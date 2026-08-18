"""
表单字段提取器（统一版）

合并了原 smart_fill.py 与 form_extractor.py 的所有提取策略：
1. 原生 input（含 checkbox/radio/file）
2. 原生 select
3. 原生 textarea
4. contenteditable 富文本区
5. 自定义下拉（role=combobox / ant-select / el-select）
6. data-oc-field 属性标记
7. 无障碍树补充（accessibility tree）

选择器策略升级：
- 从单字符串 selector 升级为多重备选数组 selectors
- 按优先级排列：id → name → aria-label → placeholder → label-for
- 不再使用脆弱的 nth-of-type fallback

字段类型推断：
- 基于标签/名称推断字段语义类型（name/email/phone/...），用于智能匹配
"""

import re
import logging
from typing import List, Dict, Any, Optional

from playwright.async_api import Page, ElementHandle

logger = logging.getLogger("offerclaw.form_extractor")


# ============================================================================
# 字段类型推断字典
# ============================================================================

# 关键词 → 字段语义类型（用于 field_matcher 规则匹配）
_FIELD_TYPE_KEYWORDS: List[Dict[str, Any]] = [
    {"keys": ["姓名", "name", "真实姓名", "fullname", "candidate_name"], "type": "name"},
    {"keys": ["手机", "电话", "phone", "mobile", "联系方式"], "type": "phone"},
    {"keys": ["邮箱", "email", "电子邮件", "e-mail", "mail"], "type": "email"},
    {"keys": ["性别", "gender", "sex"], "type": "gender"},
    {"keys": ["年龄", "age"], "type": "age"},
    {"keys": ["生日", "出生", "birth", "birthday", "dob"], "type": "birthday"},
    {"keys": ["身份证", "id_number", "idcard", "identity"], "type": "id_number"},
    {"keys": ["地址", "address"], "type": "address"},
    {"keys": ["学历", "education", "degree", "qualification"], "type": "education"},
    {"keys": ["专业", "major", "specialty"], "type": "major"},
    {"keys": ["学校", "院校", "school", "university", "college"], "type": "school"},
    {"keys": ["公司", "employer", "company"], "type": "company"},
    {"keys": ["职位", "职务", "title", "position", "job_title"], "type": "title"},
    {"keys": ["工作年限", "经验", "experience", "work_years"], "type": "experience_years"},
    {"keys": ["简历", "resume", "cv", "附件"], "type": "resume"},
    {"keys": ["技能", "skill", "技术栈"], "type": "skills"},
    {"keys": ["自我评价", "自我介绍", "个人简介", "about_me", "summary"], "type": "self_eval"},
    {"keys": ["期望薪资", "salary", "薪水"], "type": "salary"},
    {"keys": ["期望城市", "意向城市", "city", "location"], "type": "intent_city"},
    {"keys": ["证书", "qualification", "cert"], "type": "cert"},
]


def infer_field_type(label: str, name: Optional[str], input_type: str) -> str:
    """推断字段语义类型（用于智能匹配）"""
    text = f"{label or ''} {name or ''}".lower()
    for rule in _FIELD_TYPE_KEYWORDS:
        for key in rule["keys"]:
            if key.lower() in text:
                return rule["type"]
    return "unknown"


# ============================================================================
# 常见字段名映射（name 属性 → 中文标签）
# ============================================================================

_NAME_MAPPINGS = {
    "name": "姓名", "username": "用户名", "email": "邮箱", "phone": "手机号",
    "mobile": "手机号", "password": "密码", "gender": "性别", "age": "年龄",
    "birthday": "生日", "address": "地址", "city": "城市", "province": "省份",
    "school": "学校", "education": "学历", "major": "专业", "company": "公司",
    "title": "职位", "salary": "薪资", "resume": "简历", "file": "文件",
    "idcard": "身份证号", "identity": "身份证号",
}


def name_to_readable(name: str) -> str:
    """name 属性转可读中文标签"""
    name_lower = name.lower().replace("_", "").replace("-", "")
    if name_lower in _NAME_MAPPINGS:
        return _NAME_MAPPINGS[name_lower]
    # 驼峰转空格
    return re.sub(r"([a-z])([A-Z])", r"\1 \2", name).lower()


# ============================================================================
# 主提取器
# ============================================================================

class FormExtractor:
    """统一表单字段提取器"""

    async def extract_fields(self, page: Page) -> List[Dict[str, Any]]:
        """
        提取页面所有表单字段

        Returns:
            list: [{id, label, type, tag, required, selectors, options, field_type_inferred}]
                  selectors 为多重备选数组：[{type, value}]
        """
        fields: List[Dict[str, Any]] = []
        seen_keys = set()

        logger.info("开始提取表单字段...")

        def _dedup(field: Dict[str, Any]) -> bool:
            key = field.get("id") or field.get("label") or ""
            if not key or key in seen_keys:
                return False
            seen_keys.add(key)
            return True

        # 策略1：原生 input
        inputs = await page.query_selector_all(
            'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="reset"])'
        )
        for idx, el in enumerate(inputs):
            field = await self._extract_input_field(el, idx, page)
            if field and _dedup(field):
                fields.append(field)

        # 策略2：原生 select
        selects = await page.query_selector_all("select")
        for idx, el in enumerate(selects):
            field = await self._extract_select_field(el, idx, page)
            if field and _dedup(field):
                fields.append(field)

        # 策略3：原生 textarea
        textareas = await page.query_selector_all("textarea")
        for idx, el in enumerate(textareas):
            field = await self._extract_textarea_field(el, idx, page)
            if field and _dedup(field):
                fields.append(field)

        # 策略4：contenteditable
        editables = await page.query_selector_all(
            '[contenteditable="true"], [contenteditable=""]'
        )
        for idx, el in enumerate(editables):
            field = await self._extract_editable_field(el, idx, page)
            if field and _dedup(field):
                fields.append(field)

        # 策略5：自定义下拉（ant-select / el-select / role=combobox）
        custom_selects = await page.query_selector_all(
            '[role="combobox"], .ant-select-selector, .el-select, '
            '.el-select .el-input__inner, .select-trigger, [class*="dropdown-trigger"]'
        )
        for idx, el in enumerate(custom_selects):
            field = await self._extract_custom_select_field(el, idx, page)
            if field and _dedup(field):
                fields.append(field)

        # 策略6：data-oc-field 标记
        data_fields = await page.query_selector_all("[data-oc-field]")
        for idx, el in enumerate(data_fields):
            field = await self._extract_data_attribute_field(el, idx, page)
            if field and _dedup(field):
                fields.append(field)

        # 策略7：无障碍树补充（去重）
        try:
            accessibility = await page.accessibility.snapshot()
            acc_fields = self._extract_from_accessibility(accessibility)
            for acc_field in acc_fields:
                if not any(f["id"] == acc_field["id"] for f in fields):
                    fields.append(acc_field)
                    logger.info(f"  [无障碍树] 补充字段: {acc_field['label']}")
        except Exception as e:
            logger.warning(f"无障碍树提取失败: {e}")

        logger.info(f"提取到 {len(fields)} 个表单字段")
        return fields

    # ── 单元素提取 ───────────────────────────────────────────────────────

    async def _extract_input_field(
        self, el: ElementHandle, idx: int, page: Page
    ) -> Optional[Dict[str, Any]]:
        """提取 input 字段"""
        try:
            element_id = await el.get_attribute("id")
            element_name = await el.get_attribute("name")
            field_id = element_id or element_name or f"input_{idx}"

            label = await self._get_field_label(el, page)
            input_type = (await el.get_attribute("type") or "text").lower()
            required = await el.get_attribute("required") is not None
            aria_required = await el.get_attribute("aria-required")
            if aria_required and aria_required.lower() == "true":
                required = True

            placeholder = await el.get_attribute("placeholder") or ""
            aria_label = await el.get_attribute("aria-label") or ""

            # 多重备选选择器（按优先级排列）
            selectors = self._build_selectors(
                element_id=element_id,
                element_name=element_name,
                tag="input",
                input_type=input_type,
                label=label,
                placeholder=placeholder,
                aria_label=aria_label,
            )

            # 读取当前已填值（用于 keep/correct 动作规划）
            current_value = await self._get_current_value(el, "input", input_type)

            return {
                "id": field_id,
                "label": label,
                "type": input_type,
                "tag": "input",
                "required": required,
                "selector": selectors[0]["value"] if selectors else "",
                "selectors": selectors,
                "placeholder": placeholder,
                "current_value": current_value,
                "field_type_inferred": infer_field_type(label, element_name, input_type),
            }
        except Exception as e:
            logger.error(f"提取 input 字段失败: {e}")
            return None

    async def _extract_select_field(
        self, el: ElementHandle, idx: int, page: Page
    ) -> Optional[Dict[str, Any]]:
        """提取 select 字段"""
        try:
            element_id = await el.get_attribute("id")
            element_name = await el.get_attribute("name")
            field_id = element_id or element_name or f"select_{idx}"

            label = await self._get_field_label(el, page)
            required = await el.get_attribute("required") is not None

            # 提取选项
            options = await el.query_selector_all("option")
            option_texts = []
            for opt in options:
                text = await opt.inner_text()
                value = await opt.get_attribute("value")
                option_texts.append({"text": text.strip(), "value": value or text.strip()})

            selectors = self._build_selectors(
                element_id=element_id, element_name=element_name, tag="select", label=label
            )

            current_value = await self._get_current_value(el, "select", "select")

            return {
                "id": field_id,
                "label": label,
                "type": "select",
                "tag": "select",
                "required": required,
                "options": option_texts,
                "selector": selectors[0]["value"] if selectors else "",
                "selectors": selectors,
                "current_value": current_value,
                "field_type_inferred": infer_field_type(label, element_name, "select"),
            }
        except Exception as e:
            logger.error(f"提取 select 字段失败: {e}")
            return None

    async def _extract_textarea_field(
        self, el: ElementHandle, idx: int, page: Page
    ) -> Optional[Dict[str, Any]]:
        """提取 textarea 字段"""
        try:
            element_id = await el.get_attribute("id")
            element_name = await el.get_attribute("name")
            field_id = element_id or element_name or f"textarea_{idx}"

            label = await self._get_field_label(el, page)
            required = await el.get_attribute("required") is not None
            placeholder = await el.get_attribute("placeholder") or ""
            aria_label = await el.get_attribute("aria-label") or ""

            selectors = self._build_selectors(
                element_id=element_id,
                element_name=element_name,
                tag="textarea",
                label=label,
                placeholder=placeholder,
                aria_label=aria_label,
            )

            current_value = await self._get_current_value(el, "textarea", "textarea")

            return {
                "id": field_id,
                "label": label,
                "type": "textarea",
                "tag": "textarea",
                "required": required,
                "selector": selectors[0]["value"] if selectors else "",
                "selectors": selectors,
                "placeholder": placeholder,
                "current_value": current_value,
                "field_type_inferred": infer_field_type(label, element_name, "textarea"),
            }
        except Exception as e:
            logger.error(f"提取 textarea 字段失败: {e}")
            return None

    async def _extract_editable_field(
        self, el: ElementHandle, idx: int, page: Page
    ) -> Optional[Dict[str, Any]]:
        """提取 contenteditable 字段"""
        try:
            element_id = await el.get_attribute("id")
            label = await self._get_field_label(el, page)
            if not label or label == "未知字段":
                placeholder = (
                    await el.get_attribute("data-placeholder")
                    or await el.get_attribute("placeholder")
                )
                if placeholder:
                    label = placeholder.strip()

            field_id = element_id or f"editable_{idx}"

            selectors = []
            if element_id:
                selectors.append({"type": "id", "value": f"#{element_id}"})
            selectors.append({"type": "contenteditable", "value": '[contenteditable="true"]'})
            selectors.append({"type": "css", "value": f'[data-placeholder="{label}"]'})

            current_value = await self._get_current_value(el, "contenteditable", "contenteditable")

            return {
                "id": field_id,
                "label": label,
                "type": "contenteditable",
                "tag": "div",
                "required": False,
                "selector": selectors[0]["value"],
                "selectors": selectors,
                "current_value": current_value,
                "field_type_inferred": infer_field_type(label, element_id, "textarea"),
            }
        except Exception as e:
            logger.error(f"提取 contenteditable 字段失败: {e}")
            return None

    async def _extract_custom_select_field(
        self, el: ElementHandle, idx: int, page: Page
    ) -> Optional[Dict[str, Any]]:
        """提取自定义下拉（Ant Design / ElementUI / 通用 role=combobox）"""
        try:
            element_id = await el.get_attribute("id")
            label = await self._get_field_label(el, page)
            if not label or label == "未知字段":
                try:
                    parent_text = await el.evaluate(
                        """el => {
                            const wrap = el.closest('.ant-form-item, .el-form-item, .form-group, .field') || el.parentElement;
                            if (!wrap) return '';
                            const lbl = wrap.querySelector('label, .label, .ant-form-item-label, .el-form-item__label');
                            return lbl ? lbl.textContent.trim() : '';
                        }"""
                    )
                    if parent_text:
                        label = parent_text
                except Exception:
                    pass

            if not label or label == "未知字段":
                label = f"自定义下拉 {idx+1}"

            field_id = element_id or f"custom_select_{idx}"

            # 优先用 class 组合（更稳定）
            cls = await el.get_attribute("class") or ""
            selectors = []
            if cls:
                first_cls = cls.split()[0]
                selectors.append({"type": "css", "value": f".{first_cls}"})
            if element_id:
                selectors.append({"type": "id", "value": f"#{element_id}"})
            selectors.append({"type": "role", "value": '[role="combobox"]'})

            current_value = await self._get_current_value(el, "custom-select", "custom-select")

            return {
                "id": field_id,
                "label": label,
                "type": "custom-select",
                "tag": "div",
                "required": False,
                "options": [],  # 选项需点击展开才能获取
                "selector": selectors[0]["value"],
                "selectors": selectors,
                "current_value": current_value,
                "field_type_inferred": infer_field_type(label, element_id, "select"),
            }
        except Exception as e:
            logger.error(f"提取自定义下拉失败: {e}")
            return None

    async def _extract_data_attribute_field(
        self, el: ElementHandle, idx: int, page: Page
    ) -> Optional[Dict[str, Any]]:
        """提取通过 data-oc-field 标记的自定义字段"""
        try:
            field_name = await el.get_attribute("data-oc-field") or f"data_field_{idx}"
            label = (
                await el.get_attribute("data-oc-label")
                or await self._get_field_label(el, page)
                or field_name
            )
            field_type_attr = await el.get_attribute("data-oc-type") or "text"
            tag = (await el.evaluate("el => el.tagName.toLowerCase()")) or "input"
            element_id = await el.get_attribute("id")
            field_id = element_id or field_name

            selectors = []
            if element_id:
                selectors.append({"type": "id", "value": f"#{element_id}"})
            selectors.append(
                {"type": "data-attr", "value": f'[data-oc-field="{field_name}"]'}
            )

            current_value = await self._get_current_value(el, tag, field_type_attr)

            return {
                "id": field_id,
                "label": label,
                "type": field_type_attr,
                "tag": tag,
                "required": (await el.get_attribute("data-oc-required")) == "true",
                "selector": selectors[0]["value"],
                "selectors": selectors,
                "current_value": current_value,
                "field_type_inferred": infer_field_type(label, field_name, field_type_attr),
            }
        except Exception as e:
            logger.error(f"提取 data-* 字段失败: {e}")
            return None

    def _extract_from_accessibility(self, accessibility_tree: Optional[Dict]) -> List[Dict[str, Any]]:
        """从无障碍树提取字段（补充策略）"""
        fields = []

        def traverse(node):
            if not node:
                return
            if node.get("role") in ["textbox", "combobox", "checkbox", "radio", "edit"]:
                field_id = node.get("name") or f"acc_{len(fields)}"
                fields.append({
                    "id": field_id,
                    "label": node.get("name", ""),
                    "type": node.get("role"),
                    "tag": "accessibility",
                    "required": False,
                    "selector": "",
                    "selectors": [],
                    "field_type_inferred": infer_field_type(node.get("name", ""), None, node.get("role")),
                })
            for child in node.get("children", []):
                traverse(child)

        traverse(accessibility_tree)
        return fields

    # ── Label 获取（多策略）──────────────────────────────────────────────

    async def _get_current_value(self, el: ElementHandle, tag: str, input_type: str) -> str:
        """
        读取字段当前已填值（用于 keep/correct 动作规划）

        - input/textarea：e.value
        - select：选中项的 text
        - contenteditable：innerText
        - 自定义下拉：显示文本（选中项文本）
        - 读取失败返回空串，不影响提取主流程
        """
        try:
            if tag in ("input", "textarea"):
                return (await el.evaluate("e => (e.value || '').toString()")) or ""
            if tag == "select":
                return (
                    await el.evaluate(
                        """e => {
                            if (!e.selectedOptions || !e.selectedOptions.length) return '';
                            const o = e.selectedOptions[0];
                            return (o.text || o.value || '').trim();
                        }"""
                    )
                ) or ""
            if tag == "contenteditable" or input_type == "contenteditable":
                return (await el.evaluate("e => (e.innerText || '').toString().trim()")) or ""
            # 自定义下拉等：取元素自身显示文本
            return (await el.evaluate("e => (e.innerText || '').toString().trim()")) or ""
        except Exception as e:
            logger.debug(f"读取当前值失败 ({tag}/{input_type}): {e}")
            return ""

    async def _get_field_label(self, el: ElementHandle, page: Page) -> str:
        """多策略获取字段标签"""
        # 1. aria-label
        aria_label = await el.get_attribute("aria-label")
        if aria_label:
            return aria_label.strip()

        # 2. <label for="id">
        element_id = await el.get_attribute("id")
        if element_id:
            try:
                label_el = await page.query_selector(f'label[for="{element_id}"]')
                if label_el:
                    return (await label_el.inner_text()).strip()
            except Exception as e:
                logger.debug(f"策略2获取 label 失败: {e}")

        # 3. placeholder
        placeholder = await el.get_attribute("placeholder")
        if placeholder:
            return placeholder.strip()

        # 4. name 属性（驼峰/下划线转可读）
        name = await el.get_attribute("name")
        if name:
            return name_to_readable(name)

        # 5. 相邻 label 元素
        try:
            parent = await el.evaluate_handle("el => el.parentElement")
            label_el = await parent.query_selector("label")
            if label_el:
                return (await label_el.inner_text()).strip()
        except Exception as e:
            logger.debug(f"策略5获取相邻 label 失败: {e}")

        return "未知字段"

    # ── 多步骤向导检测 ─────────────────────────────────────────────────

    async def detect_wizard_steps(self, page: Page) -> Dict[str, Any]:
        """
        检测页面是否为多步骤向导表单

        识别策略（任一命中即判定为多步骤）：
        1. 步骤指示器：[class*="step"] / .ant-steps / .el-steps / [role="progressbar"][aria-valuenow]
        2. 步骤标题列表：含 "基本信息/教育经历/工作经历" 等分步标题
        3. 分页按钮：含 "上一步/下一步/Previous/Next" 且页面有 form

        Returns:
            {
                "is_multi_step": bool,
                "current_step": int (1-based, 0 表示无法判断),
                "total_steps": int (0 表示无法判断),
                "step_titles": List[str],
                "next_button_selector": Optional[str],  # 「下一步」按钮选择器
                "prev_button_selector": Optional[str],
                "submit_button_selector": Optional[str],  # 最后一步的提交按钮
            }
        """
        result = {
            "is_multi_step": False,
            "current_step": 0,
            "total_steps": 0,
            "step_titles": [],
            "next_button_selector": None,
            "prev_button_selector": None,
            "submit_button_selector": None,
        }

        try:
            info = await page.evaluate(
                """() => {
                    const r = {
                        is_multi_step: false,
                        current_step: 0,
                        total_steps: 0,
                        step_titles: [],
                        next_btn: null,
                        prev_btn: null,
                        submit_btn: null,
                    };

                    // 1. Ant Design Steps
                    const antSteps = document.querySelectorAll('.ant-steps .ant-steps-item');
                    if (antSteps.length >= 2) {
                        r.is_multi_step = true;
                        r.total_steps = antSteps.length;
                        antSteps.forEach((it, i) => {
                            const title = it.querySelector('.ant-steps-item-title');
                            if (title) r.step_titles.push(title.textContent.trim());
                            if (it.classList.contains('ant-steps-item-process')) {
                                r.current_step = i + 1;
                            }
                        });
                    }

                    // 2. ElementUI Steps
                    if (!r.is_multi_step) {
                        const elSteps = document.querySelectorAll('.el-steps .el-step');
                        if (elSteps.length >= 2) {
                            r.is_multi_step = true;
                            r.total_steps = elSteps.length;
                            elSteps.forEach((it, i) => {
                                const title = it.querySelector('.el-step__title');
                                if (title) r.step_titles.push(title.textContent.trim());
                                if (it.classList.contains('is-process')) {
                                    r.current_step = i + 1;
                                }
                            });
                        }
                    }

                    // 3. 通用 step class（含 "step" 关键词的列表项）
                    if (!r.is_multi_step) {
                        const stepEls = document.querySelectorAll(
                            '[class*="step-item"], [class*="StepItem"], [class*="step-item-active"], ' +
                            '[data-step], .wizard-step, .progress-step'
                        );
                        if (stepEls.length >= 2) {
                            r.is_multi_step = true;
                            r.total_steps = stepEls.length;
                            stepEls.forEach((it, i) => {
                                const txt = (it.textContent || '').trim().slice(0, 30);
                                if (txt) r.step_titles.push(txt);
                                const cls = it.className || '';
                                if (/active|current|process/i.test(cls)) {
                                    r.current_step = i + 1;
                                }
                            });
                        }
                    }

                    // 4. 分页按钮兜底（即使没有步骤指示器，但有"下一步"按钮也判定为多步骤）
                    const allBtns = Array.from(document.querySelectorAll(
                        'button, a.btn, [role="button"], .btn, [class*="btn"]'
                    ));
                    const nextKeywords = ['下一步', '下一页', 'next', 'continue', '继续'];
                    const prevKeywords = ['上一步', '上一页', 'previous', 'prev', '返回'];
                    const submitKeywords = ['提交', '确认提交', '完成', 'submit', 'finish'];

                    for (const b of allBtns) {
                        const txt = (b.textContent || '').trim().toLowerCase();
                        if (!txt || txt.length > 20) continue;
                        // 下一步
                        if (!r.next_btn && nextKeywords.some(k => txt.includes(k.toLowerCase()))) {
                            r.next_btn = b;
                            if (!r.is_multi_step) r.is_multi_step = true;
                        }
                        // 上一步
                        if (!r.prev_btn && prevKeywords.some(k => txt.includes(k.toLowerCase()))) {
                            r.prev_btn = b;
                        }
                        // 提交
                        if (!r.submit_btn && submitKeywords.some(k => txt.includes(k.toLowerCase()))) {
                            r.submit_btn = b;
                        }
                    }

                    // 为按钮生成选择器
                    function selectorFor(el) {
                        if (!el) return null;
                        if (el.id) return '#' + el.id;
                        // 用文本内容生成 xpath 式选择器（由调用方用 page.locator 定位）
                        const txt = (el.textContent || '').trim();
                        return txt ? 'text=' + txt.slice(0, 20) : null;
                    }
                    r.next_btn_selector = selectorFor(r.next_btn);
                    r.prev_btn_selector = selectorFor(r.prev_btn);
                    r.submit_btn_selector = selectorFor(r.submit_btn);

                    // 清理按钮引用（无法序列化 DOM 元素）
                    r.next_btn = null;
                    r.prev_btn = null;
                    r.submit_btn = null;

                    return r;
                }"""
            )

            result.update(info)
            # 类型修正
            result["is_multi_step"] = bool(result.get("is_multi_step"))
            result["step_titles"] = list(result.get("step_titles") or [])

        except Exception as e:
            logger.warning(f"多步骤向导检测失败: {e}")

        return result

    # ── 选择器构建（多重备选）──────────────────────────────────────────

    def _build_selectors(
        self,
        element_id: Optional[str] = None,
        element_name: Optional[str] = None,
        tag: str = "input",
        input_type: Optional[str] = None,
        label: Optional[str] = None,
        placeholder: Optional[str] = None,
        aria_label: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """
        构建多重备选选择器（按优先级排列）

        不再使用脆弱的 nth-of-type fallback。
        找不到元素由填写逻辑的多重兜底处理（见 auto_filler._fill_one 的 findField）。
        """
        selectors: List[Dict[str, str]] = []

        # 1. ID（最稳定）
        if element_id:
            selectors.append({"type": "id", "value": f"#{element_id}"})

        # 2. name 属性
        if element_name:
            tag_suffix = f'[type="{input_type}"]' if input_type and tag == "input" and input_type not in ("text", "") else ""
            selectors.append({
                "type": "name",
                "value": f'{tag}[name="{element_name}"]{tag_suffix}',
            })

        # 3. aria-label
        if aria_label:
            selectors.append({
                "type": "aria-label",
                "value": f'[aria-label="{aria_label}"]',
            })

        # 4. placeholder
        if placeholder:
            selectors.append({
                "type": "placeholder",
                "value": f'{tag}[placeholder="{placeholder}"]',
            })

        # 5. label[for] 关联（需要填写时按 label 文本反查）
        if label and label != "未知字段":
            selectors.append({
                "type": "label-for",
                "value": f'label[for]:"{label}"',  # 占位，实际由 JS findField 处理
            })

        return selectors
