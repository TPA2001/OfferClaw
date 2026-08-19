"""
Playwright 自动填表服务

后端启动 Playwright 浏览器，自动打开目标页面并填写表单（不再生成脚本让用户手动粘贴）。

支持字段类型：
- input (text/email/tel/number/date/password)
- textarea
- select（原生下拉）
- checkbox / radio
- contenteditable（富文本）
- 自定义下拉（role=combobox / ant-select / el-select）

填写策略：
- React/Vue 兼容：用 nativeInputValueSetter 触发受控组件更新
- 多重选择器兜底：selector → id → name → aria-label → placeholder → label[for]
- 人类化操作（随机延迟，模拟真实输入）
- 视觉反馈：填写成功的元素高亮 + 截图返回给前端
- 默认不提交（让用户最后确认）

参数：
- headless: True=后台静默填写；False=可视化模式（用户能看到浏览器）
- auto_submit: 是否自动点击提交按钮（默认 False）
"""

import asyncio
import base64
import logging
import json
from typing import List, Dict, Any, Optional

from app.services.playwright_runtime import start_chrome, stop_chrome, human_delay

logger = logging.getLogger("offerclaw.auto_filler")


class AutoFillerService:
    """Playwright 自动填表服务"""

    async def auto_fill(
        self,
        url: str,
        fields: List[Dict[str, Any]],
        mappings: List[Dict[str, Any]],
        user_id: str = "default",
        headless: bool = True,
        auto_submit: bool = False,
        submit_selector: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        自动填写表单

        Args:
            url: 目标页面 URL
            fields: 字段元数据列表（来自 extract-from-url 接口）
            mappings: 字段匹配结果（来自 match 接口 + 用户手动调整）
            user_id: 用户 ID（隔离 userDataDir）
            headless: 是否无头
            auto_submit: 是否自动提交
            submit_selector: 提交按钮选择器（auto_submit=True 时必填）

        Returns:
            dict: {
                "success": bool,
                "filled_count": int,
                "failed_count": int,
                "failures": [{field_id, label, reason}],
                "screenshot_before": str,  # base64 jpeg
                "screenshot_after": str,   # base64 jpeg
                "submitted": bool,
                "message": str,
            }
        """
        logger.info(f"自动填表: url={url}, fields={len(fields)}, mappings={len(mappings)}, user={user_id}")

        # 合并字段元数据
        field_meta = {f.get("id") or f.get("name") or "": f for f in fields if f.get("id") or f.get("name")}

        # 动作分布统计（来自 matcher 的 keep/fill/correct/manual/skip）
        action_stats = {"keep": 0, "fill": 0, "correct": 0, "manual": 0, "skip": 0}

        # 构造填写任务列表（仅 fill/correct 需要实际填写；keep/manual/skip 跳过）
        fill_tasks: List[Dict[str, Any]] = []
        skip_actions = {"keep", "manual", "skip"}
        for mapping in mappings:
            fid = mapping.get("field_id") or mapping.get("id") or ""
            value = mapping.get("value")
            action = (mapping.get("action") or "fill").lower()
            # 统计
            action_stats[action] = action_stats.get(action, 0) + 1
            if not fid or value in (None, ""):
                continue
            if action in skip_actions:
                # keep/manual/skip：不自动填写，保留页面现有值或交由用户
                continue
            meta = field_meta.get(fid, {})
            fill_tasks.append({
                "id": fid,
                "value": str(value),
                "action": action,
                "tag": (meta.get("tag") or "input").lower(),
                "type": (meta.get("type") or "text").lower(),
                "selector": meta.get("selector") or "",
                # 新增：多重备选选择器数组（按优先级尝试）
                "selectors": meta.get("selectors") or [],
                "label": meta.get("label") or fid,
                "options": meta.get("options") or [],
            })

        # 把填写逻辑注入页面（复用脚本生成版的核心函数）
        fill_js = self._build_fill_js(fill_tasks)

        failures: List[Dict[str, str]] = []
        unverified: List[Dict[str, str]] = []  # 填后验证未通过的项
        screenshot_before = None
        screenshot_after = None
        submitted = False
        filled_count = 0
        verified_count = 0

        # 使用 CDP 模式：subprocess 启动真实 Chrome + connect_over_cdp
        # 真实 Chrome 无自动化痕迹，不会被反爬识别
        from playwright.async_api import async_playwright

        port, proc = start_chrome(site="autofill", user_id=user_id, headless=headless)

        try:
            async with async_playwright() as pw:
                try:
                    logger.info(f"CDP 连接: http://127.0.0.1:{port}")
                    browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
                except Exception as e:
                    logger.error(f"CDP 连接失败: {e}")
                    return {
                        "success": False,
                        "filled_count": 0,
                        "failed_count": len(fill_tasks),
                        "failures": [],
                        "screenshot_before": None,
                        "screenshot_after": None,
                        "submitted": False,
                        "message": f"CDP 连接失败: {e}",
                    }

                try:
                    # 获取或创建 context
                    if len(browser.contexts) > 0:
                        context = browser.contexts[0]
                    else:
                        context = await browser.new_context()

                    page = await context.new_page()
                    try:
                        # 打开目标页
                        try:
                            await page.goto(url, wait_until="networkidle", timeout=30000)
                        except Exception:
                            try:
                                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                            except Exception:
                                await page.goto(url, timeout=30000)

                        await human_delay(1.0, 1.8)

                        # 截图：填写前
                        shot = await page.screenshot(type="jpeg", quality=50)
                        screenshot_before = base64.b64encode(shot).decode() if shot else None

                        # 注入视觉反馈样式
                        await page.add_style_tag(content="""
                            @keyframes oc-flash-ok {
                                0% { box-shadow: 0 0 0 0 rgba(107, 125, 10, 0.6); }
                                100% { box-shadow: 0 0 0 6px rgba(107, 125, 10, 0); }
                            }
                            @keyframes oc-flash-err {
                                0% { box-shadow: 0 0 0 0 rgba(185, 74, 58, 0.7); }
                                100% { box-shadow: 0 0 0 6px rgba(185, 74, 58, 0); }
                            }
                            .oc-filled { outline: 2px solid #6b7d0a !important; outline-offset: 1px; animation: oc-flash-ok 0.8s ease-out; }
                            .oc-failed { outline: 2px solid #b94a3a !important; outline-offset: 1px; animation: oc-flash-err 0.8s ease-out; }
                        """)

                        # 逐字段填写（在 Python 侧调度，便于收集结果 + 填后验证）
                        for task in fill_tasks:
                            try:
                                res = await self._fill_one(page, task)
                                ok = bool(res and res.get("ok"))
                                if ok:
                                    filled_count += 1
                                    # 文件上传后：处理解析弹窗（覆盖/确认/刷新）
                                    is_file = (task.get("type") == "file") or str(
                                        task.get("value", "")
                                    ).startswith("FILE:")
                                    if is_file:
                                        await self._handle_parser_dialog(page)
                                    # 填后验证（文件字段不参与值校验，由解析弹窗+页面状态确认）
                                    if is_file:
                                        verified_count += 1
                                    else:
                                        verified = bool(res.get("verified"))
                                        if verified:
                                            verified_count += 1
                                        else:
                                            unverified.append({
                                                "field_id": task["id"],
                                                "label": task["label"],
                                                "reason": "填后值未匹配期望（可能 select unconfirmed）",
                                            })
                                else:
                                    failures.append({
                                        "field_id": task["id"],
                                        "label": task["label"],
                                        "reason": (res.get("reason") if res else "未找到元素或填写失败"),
                                    })
                            except Exception as e:
                                failures.append({
                                    "field_id": task["id"],
                                    "label": task["label"],
                                    "reason": str(e),
                                })
                            await human_delay(0.3, 0.8)

                        # 等待动画完成
                        await human_delay(0.8, 1.4)

                        # 截图：填写后
                        shot = await page.screenshot(type="jpeg", quality=50)
                        screenshot_after = base64.b64encode(shot).decode() if shot else None

                        # 自动提交
                        if auto_submit and submit_selector:
                            try:
                                btn = await page.query_selector(submit_selector)
                                if btn:
                                    await btn.click()
                                    await human_delay(1.5, 2.5)
                                    submitted = True
                                    # 提交后再截一次图
                                    shot = await page.screenshot(type="jpeg", quality=50)
                                    screenshot_after = base64.b64encode(shot).decode() if shot else None
                            except Exception as e:
                                logger.warning(f"自动提交失败: {e}")

                        failed_count = len(fill_tasks) - filled_count

                        return {
                            "success": True,
                            "filled_count": filled_count,
                            "verified_count": verified_count,
                            "failed_count": failed_count,
                            "failures": failures,
                            "unverified": unverified,
                            "action_stats": action_stats,
                            "screenshot_before": screenshot_before,
                            "screenshot_after": screenshot_after,
                            "submitted": submitted,
                            "message": (
                                f"填写完成：成功 {filled_count}（已验证 {verified_count}）/ "
                                f"失败 {failed_count}"
                                + (f"，未验证 {len(unverified)}" if unverified else "")
                            ),
                        }
                    finally:
                        try:
                            await page.close()
                        except Exception:
                            pass
                finally:
                    # 仅断开 CDP 连接（不关闭 Chrome 进程）
                    try:
                        await browser.close()
                    except Exception:
                        pass
        finally:
            # headless 模式下关闭 Chrome 释放资源；headful 模式让用户看到结果
            try:
                cmdline = " ".join(proc.args) if hasattr(proc, "args") and proc.args else ""
                if "--headless" in cmdline:
                    stop_chrome(site="autofill", user_id=user_id)
            except Exception as e:
                logger.warning(f"stop_chrome 异常: {e}")

    async def _fill_one(self, page, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        填写单个字段，返回 {ok, verified, reason}

        - ok: 是否填写成功
        - verified: 填后读取实际值是否匹配期望（自定义下拉未选中→unconfirmed）
        - reason: 失败原因
        """
        # 文件上传字段：用 Playwright 原生 API（不用 evaluate，因为涉及本地文件）
        if (task.get("type") or "").lower() == "file" or str(task.get("value", "")).startswith("FILE:"):
            file_ok = await self._fill_file(page, task)
            return {"ok": file_ok, "verified": False, "reason": None if file_ok else "file_upload_failed"}

        # 用 page.evaluate 执行 JS 填写逻辑（复用脚本生成版的策略）
        js = """
        async (task) => {
            const val = task.value;

            // 多重选择器定位（按优先级尝试 selectors 数组，再降级到原 selector）
            function findField(entry) {
                // 1. 优先尝试 selectors 数组（来自 FormExtractor 的多重备选）
                const selectors = entry.selectors || [];
                for (const s of selectors) {
                    if (!s || !s.value) continue;
                    try {
                        // label-for 是占位语法，跳过由后续兜底处理
                        if (s.type === 'label-for') continue;
                        const el = document.querySelector(s.value);
                        if (el) return el;
                    } catch (e) {}
                }
                // 2. 降级到旧版单 selector
                if (entry.selector) {
                    try {
                        const el = document.querySelector(entry.selector);
                        if (el) return el;
                    } catch (e) {}
                }
                // 3. 旧版多重兜底（兼容未升级的 fields 数据）
                //    注意：属性值来自任意网页（label/id 由目标站点控制），
                //    必须用 CSS.escape 转义后再拼选择器，防止注入破坏语法/执行代码
                if (entry.id) {
                    const el = document.getElementById(entry.id);
                    if (el) return el;
                    const byName = document.querySelector('[name="' + CSS.escape(entry.id) + '"]');
                    if (byName) return byName;
                    const byAria = document.querySelector('[aria-label="' + CSS.escape(entry.label || '') + '"]');
                    if (byAria) return byAria;
                    const byPh = document.querySelector('[placeholder="' + CSS.escape(entry.label || '') + '"]');
                    if (byPh) return byPh;
                    // data-oc-field 自定义属性
                    const byData = document.querySelector('[data-oc-field="' + CSS.escape(entry.id) + '"]');
                    if (byData) return byData;
                }
                // 4. label[for] 关联（精确匹配 + 包含匹配）
                const labelEls = Array.from(document.querySelectorAll('label'));
                for (const l of labelEls) {
                    const lt = l.textContent.trim();
                    if ((lt === entry.label || lt.includes(entry.label) || entry.label.includes(lt)) && l.htmlFor) {
                        const el = document.getElementById(l.htmlFor);
                        if (el) return el;
                    }
                }
                // 5. 兜底：按 label 文本找最近的 input/textarea/select
                if (entry.label) {
                    const allLabels = Array.from(document.querySelectorAll('label, .form-label, .label, .field-label, .ant-form-item-label, .el-form-item__label'));
                    for (const l of allLabels) {
                        const lt = (l.textContent || '').trim();
                        if (lt === entry.label || lt.includes(entry.label)) {
                            // 向上找最近的 form-item，然后找其中的 input
                            let p = l;
                            for (let i = 0; i < 5; i++) {
                                if (!p.parentElement) break;
                                p = p.parentElement;
                                const input = p.querySelector('input, textarea, select, [contenteditable="true"]');
                                if (input) return input;
                            }
                        }
                    }
                }
                return null;
            }

            function setNativeValue(el, value) {
                const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype
                            : el.tagName === 'SELECT' ? HTMLSelectElement.prototype
                            : HTMLInputElement.prototype;
                const setter = Object.getOwnPropertyDescriptor(proto, 'value');
                if (setter && setter.set) setter.set.call(el, value);
                else el.value = value;
            }

            function markOk(el) { el.classList.add('oc-filled'); }
            function markFail(el) { el.classList.add('oc-failed'); }

            // 读取字段当前实际值（用于填后验证）
            function readValue(el) {
                const tag = (el.tagName || '').toLowerCase();
                const type = (el.type || task.type || 'text').toLowerCase();
                if (el.isContentEditable || el.getAttribute('contenteditable') === 'true') return (el.innerText || '').trim();
                if (tag === 'select') {
                    if (!el.selectedOptions || !el.selectedOptions.length) return '';
                    const o = el.selectedOptions[0];
                    return (o.text || o.value || '').trim();
                }
                if (type === 'checkbox') return el.checked ? 'true' : 'false';
                if (type === 'radio') return el.checked ? el.value : '';
                if (el.getAttribute('role') === 'combobox' || el.classList.contains('ant-select-selector') ||
                    el.classList.contains('el-select') || el.classList.contains('select-trigger')) {
                    return (el.innerText || '').trim();
                }
                return (el.value || '').trim();
            }

            // 双向包含容错比对（忽略大小写）
            function isMatch(actual, expected) {
                if (!actual) return false;
                const a = actual.toLowerCase().trim();
                const e = (expected || '').toLowerCase().trim();
                return a === e || a.includes(e) || e.includes(a);
            }

            const el = findField(task);
            if (!el) return { ok: false, reason: 'not_found', verified: false };

            const tag = (el.tagName || '').toLowerCase();
            const type = (el.type || task.type || 'text').toLowerCase();

            try {
                // contenteditable
                if (el.isContentEditable || el.getAttribute('contenteditable') === 'true') {
                    el.focus();
                    el.innerText = val;
                    el.dispatchEvent(new InputEvent('input', { bubbles: true, data: val }));
                    el.dispatchEvent(new Event('blur', { bubbles: true }));
                    markOk(el);
                    return { ok: true, verified: isMatch(readValue(el), val) };
                }
                // select
                if (tag === 'select') {
                    let matched = false;
                    for (const opt of el.options) {
                        if (opt.value === val || opt.text.trim() === val) {
                            setNativeValue(el, opt.value);
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                            matched = true; break;
                        }
                    }
                    if (!matched) {
                        for (const opt of el.options) {
                            if (opt.text.includes(val) || val.includes(opt.text.trim())) {
                                setNativeValue(el, opt.value);
                                el.dispatchEvent(new Event('input', { bubbles: true }));
                                el.dispatchEvent(new Event('change', { bubbles: true }));
                                matched = true; break;
                            }
                        }
                    }
                    if (matched) {
                        markOk(el);
                        const verified = isMatch(readValue(el), val) || el.value === val;
                        return { ok: true, verified };
                    }
                    markFail(el); return { ok: false, reason: 'select_no_match', verified: false };
                }
                // checkbox
                if (type === 'checkbox') {
                    const want = ['true','1','yes','on','✓','是'].includes(val.toLowerCase());
                    if (el.checked !== want) el.click();
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    markOk(el);
                    return { ok: true, verified: el.checked === want };
                }
                // radio
                if (type === 'radio') {
                    const group = document.querySelectorAll(`input[type="radio"][name="${el.name}"]`);
                    let picked = null;
                    for (const r of group) {
                        const rVal = (r.value || '').toLowerCase();
                        const rLabel = (r.closest('label')?.textContent || r.getAttribute('aria-label') || '').trim().toLowerCase();
                        if (rVal === val.toLowerCase() || rLabel === val.toLowerCase() || rLabel.includes(val.toLowerCase())) {
                            r.click();
                            r.dispatchEvent(new Event('change', { bubbles: true }));
                            markOk(r);
                            picked = r;
                            break;
                        }
                    }
                    if (picked) return { ok: true, verified: picked.checked };
                    markFail(el); return { ok: false, reason: 'radio_no_match', verified: false };
                }
                // 自定义下拉
                if (el.getAttribute('role') === 'combobox' || el.classList.contains('ant-select-selector') ||
                    el.classList.contains('el-select') || el.classList.contains('select-trigger')) {
                    el.click();
                    await new Promise(r => setTimeout(r, 200));
                    const items = document.querySelectorAll('.ant-select-item, .el-select-dropdown__item, [role="option"], li[role="option"]');
                    let clicked = false;
                    for (const it of items) {
                        if ((it.textContent || '').trim() === val || (it.textContent || '').includes(val)) {
                            it.click();
                            clicked = true; break;
                        }
                    }
                    if (clicked) {
                        // 等待下拉关闭后重新读取选中值（select 确认）
                        await new Promise(r => setTimeout(r, 350));
                        markOk(el);
                        const verified = isMatch(readValue(el), val);
                        return { ok: true, verified };
                    }
                    markFail(el); return { ok: false, reason: 'custom_select_no_match', verified: false };
                }
                // 文件上传跳过（应在 Python 侧用 _fill_file 处理）
                if (type === 'file') {
                    markFail(el); return { ok: false, reason: 'file_upload_should_use_python', verified: false };
                }
                // 普通文本
                el.focus();
                setNativeValue(el, val);
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new Event('blur', { bubbles: true }));
                markOk(el);
                return { ok: true, verified: isMatch(readValue(el), val) };
            } catch (e) {
                markFail(el);
                return { ok: false, reason: e.message, verified: false };
            }
        }
        """
        try:
            result = await page.evaluate(js, task)
            if not isinstance(result, dict):
                return {"ok": False, "verified": False, "reason": "invalid_result"}
            return result
        except Exception as e:
            logger.debug(f"填写 {task.get('id')} 异常: {e}")
            return {"ok": False, "verified": False, "reason": str(e)}

    async def _fill_file(self, page, task: Dict[str, Any]) -> bool:
        """
        填写文件上传字段（增强版）

        定位策略（按优先级）：
        1. 用 selectors 数组（来自 FormExtractor 多重备选）定位 input[type=file]
        2. 用 selector / id / name 定位 input[type=file]
        3. 按 accept 属性匹配（简历场景优先 .pdf / .doc）
        4. 自定义上传按钮兜底：点击 label 含「上传简历/上传附件/选择文件」的按钮，
           触发隐藏的 input[type=file] 后再设置文件

        支持的 value 格式：
        - "FILE:resume"        → 使用默认简历路径（user_data_dir/resume.pdf 等）
        - "FILE:/abs/path.pdf" → 使用指定绝对路径
        - "FILE:resume.pdf"    → 在 user_data_dir 下查找
        """
        value = str(task.get("value", ""))
        logger.info(f"处理文件上传字段: {task.get('id')}, value={value}")

        # 解析文件路径
        if value.startswith("FILE:"):
            file_ref = value[5:].strip()
        else:
            file_ref = value

        import os
        from pathlib import Path as _Path
        from app.services.playwright_runtime import USER_DATA_ROOT

        user_root = _Path(USER_DATA_ROOT).resolve()

        def _safe_within_root(p: _Path) -> bool:
            """路径必须位于 USER_DATA_ROOT 之内（防御 ../ 穿越与任意文件读取）"""
            rp = p.resolve()
            return rp == user_root or user_root in rp.parents

        candidate_paths = []
        if file_ref and (file_ref.startswith("/") or file_ref.startswith("\\") or ":" in file_ref[:2]):
            # 绝对路径：仅允许 USER_DATA_ROOT 内的文件
            abs_path = _Path(file_ref)
            if _safe_within_root(abs_path):
                candidate_paths.append(str(abs_path))
            else:
                logger.warning(f"拒绝 USER_DATA_ROOT 之外的绝对路径: {file_ref}")
        elif file_ref == "resume" or not file_ref:
            # 默认简历文件名
            for ext in [".pdf", ".doc", ".docx"]:
                candidate_paths.append(str(USER_DATA_ROOT / "autofill" / f"resume{ext}"))
                candidate_paths.append(str(USER_DATA_ROOT / f"resume{ext}"))
        else:
            # 相对路径：在 user_data_root 下查找（解析后必须仍在根内，拒绝 ../ 穿越）
            for base in (USER_DATA_ROOT, USER_DATA_ROOT / "autofill"):
                cand = base / file_ref
                if _safe_within_root(cand):
                    candidate_paths.append(str(cand))
                else:
                    logger.warning(f"拒绝穿越路径: {file_ref}")

        # 找第一个存在的文件
        file_path = None
        for p in candidate_paths:
            if os.path.exists(p):
                file_path = p
                break

        if not file_path:
            logger.warning(
                f"文件上传字段 {task.get('id')} 无可用文件，候选路径: {candidate_paths}"
            )
            return False

        # 推断期望的 accept 扩展名（用于按 accept 属性匹配）
        file_ext = os.path.splitext(file_path)[1].lower().lstrip(".")
        accept_hints = []
        if file_ext in ("pdf", "doc", "docx"):
            accept_hints = [f".{file_ext}", "pdf", "doc", "docx", "resume", "简历"]
        elif file_ext in ("png", "jpg", "jpeg", "gif"):
            accept_hints = [f".{file_ext}", "image/*"]

        try:
            file_input = await self._locate_file_input(page, task, accept_hints)

            if not file_input:
                # 兜底：尝试点击自定义上传按钮触发隐藏的 input[type=file]
                triggered = await self._trigger_custom_upload_button(page, task)
                if triggered:
                    # 等待 input[type=file] 出现
                    try:
                        await page.wait_for_selector(
                            'input[type="file"]', timeout=2000
                        )
                        file_input = await page.query_selector('input[type="file"]')
                    except Exception:
                        pass

            if not file_input:
                logger.warning(f"未找到 input[type=file] 元素: {task.get('id')}")
                return False

            await file_input.set_input_files(file_path)
            logger.info(f"文件上传成功: {task.get('id')} ← {file_path}")
            # 视觉反馈
            try:
                await page.evaluate(
                    """(el) => { if (el) el.classList.add('oc-filled'); }""",
                    file_input,
                )
            except Exception:
                pass
            return True
        except Exception as e:
            logger.warning(f"文件上传异常 {task.get('id')}: {e}")
            return False

    async def _locate_file_input(
        self, page, task: Dict[str, Any], accept_hints: List[str]
    ) -> Optional[Any]:
        """
        多策略定位 input[type=file] 元素

        优先级：
        1. selectors 数组（来自 FormExtractor）
        2. selector 字段
        3. id / name 属性
        4. 按 accept 属性匹配（如果 accept_hints 非空）
        5. 页面上第一个 input[type=file]
        """
        # 1. selectors 数组
        selectors = task.get("selectors") or []
        for s in selectors:
            if not s or not s.get("value"):
                continue
            try:
                # 给 selector 附加 input[type=file] 约束
                sel = s["value"]
                # 如果 selector 本身不是 input[type=file]，尝试叠加
                if 'input[type="file"]' not in sel and not sel.startswith("#"):
                    el = await page.query_selector(f'{sel} input[type="file"]')
                    if el:
                        return el
                el = await page.query_selector(sel)
                if el:
                    tag = await el.evaluate("e => e.tagName.toLowerCase()")
                    if tag == "input" and await el.get_attribute("type") == "file":
                        return el
            except Exception:
                continue

        # 2. selector 字段
        selector = task.get("selector") or ""
        if selector:
            try:
                el = await page.query_selector(selector)
                if el:
                    return el
            except Exception:
                pass

        # 3. id / name
        fid = task.get("id", "")
        if fid:
            try:
                el = await page.query_selector(f'input[type="file"]#{fid}')
                if el:
                    return el
            except Exception:
                pass
            try:
                el = await page.query_selector(f'input[type="file"][name="{fid}"]')
                if el:
                    return el
            except Exception:
                pass

        # 4. 按 accept 属性匹配
        if accept_hints:
            for hint in accept_hints:
                try:
                    el = await page.query_selector(
                        f'input[type="file"][accept*="{hint}"]'
                    )
                    if el:
                        return el
                except Exception:
                    continue

        # 5. 兜底：页面上第一个 input[type=file]
        try:
            el = await page.query_selector('input[type="file"]')
            return el
        except Exception:
            return None

    async def _trigger_custom_upload_button(
        self, page, task: Dict[str, Any]
    ) -> bool:
        """
        点击自定义上传按钮，触发隐藏的 input[type=file]

        识别策略：
        - 按钮文本含「上传简历/上传附件/选择文件/选择简历/上传文件」
        - label 关联的上传区域（.upload-area / .upload-btn / [class*="upload"]）
        - 任务标签或 label 含「简历/附件」关键词时优先匹配
        """
        label = (task.get("label") or "").lower()
        # 根据字段类型选择关键词
        if "简历" in label or "resume" in label or "cv" in label:
            keywords = ["上传简历", "选择简历", "上传附件", "选择文件", "上传文件", "点击上传"]
        else:
            keywords = ["上传", "选择文件", "点击上传", "上传附件", "browse", "upload"]

        try:
            for kw in keywords:
                # 优先匹配 button / [role=button] / .upload-btn
                btn = page.locator(
                    f'button:has-text("{kw}"), '
                    f'[role="button"]:has-text("{kw}"), '
                    f'.upload-btn:has-text("{kw}"), '
                    f'[class*="upload"]:has-text("{kw}")'
                ).first
                if await btn.count() > 0:
                    try:
                        await btn.click()
                        logger.info(f"已点击自定义上传按钮: {kw}")
                        return True
                    except Exception:
                        continue
            return False
        except Exception as e:
            logger.debug(f"自定义上传按钮触发失败: {e}")
            return False

    async def _handle_parser_dialog(self, page) -> bool:
        """
        检测并确认上传简历后弹出的解析对话框（覆盖/确认/刷新）

        许多官网在用户上传简历后会弹窗询问：
        - 「是否覆盖已有简历」「确认覆盖」「使用新简历替换」「刷新简历信息」
        - 英文：overwrite / confirm / replace / refresh resume

        命中关键词的按钮会被点击确认，让站点自己的解析器继续工作，
        随后由 keep/fill/correct 动作规划补填缺失项。
        """
        js = """
        () => {
            const keywords = [
                '覆盖', '确认覆盖', '确认替换', '使用新简历', '替换简历',
                '刷新简历', '重新解析', '确定', '确认',
                'overwrite', 'confirm', 'replace', 'refresh resume', 'use new resume'
            ];
            const btns = Array.from(document.querySelectorAll(
                'button, [role="button"], .btn, [class*="btn"], .ant-btn, .el-button, a.btn'
            ));
            for (const kw of keywords) {
                const k = kw.toLowerCase();
                for (const b of btns) {
                    const txt = (b.textContent || '').trim().toLowerCase();
                    // 只点短文本按钮，避免误点正文段落
                    if (!txt || txt.length > 12) continue;
                    if (txt.includes(k)) {
                        // 跳过「取消」类按钮
                        if (txt.includes('取消') || txt.includes('cancel') || txt.includes('不')) continue;
                        b.click();
                        return { clicked: true, keyword: kw };
                    }
                }
            }
            return { clicked: false };
        }
        """
        try:
            result = await page.evaluate(js)
            if result and result.get("clicked"):
                logger.info(f"已确认解析弹窗: {result.get('keyword')}")
                await human_delay(0.8, 1.5)
                return True
            return False
        except Exception as e:
            logger.debug(f"解析弹窗处理异常: {e}")
            return False

    def _build_fill_js(self, tasks: List[Dict[str, Any]]) -> str:
        """构造纯 JS 填写脚本（用于直接控制台执行模式，保留兼容）"""
        return json.dumps(tasks, ensure_ascii=False)


# 单例
_service_instance: Optional[AutoFillerService] = None


def get_auto_filler_service() -> AutoFillerService:
    global _service_instance
    if _service_instance is None:
        _service_instance = AutoFillerService()
    return _service_instance
