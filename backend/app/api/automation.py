"""
智能填写 API
提供表单字段提取、匹配、填写的 HTTP 接口
支持 Web 版本（无需插件）
同时提供 Boss 直聘岗位搜索能力
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import logging
import json

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.response import ok, BadRequestError, InternalServerError
from app.services.smart_fill import get_smart_fill_service
from app.services.boss_search import get_boss_search_service
from app.services.auto_filler import get_auto_filler_service
from app.services.playwright_runtime import (
    check_boss_login,
    open_boss_login,
    BOSS_LOGIN_URL,
)
from app.automation import FieldMatcher
from sqlalchemy.orm import Session
from app.models.profile import Profile


logger = logging.getLogger("offerclaw.automation")

router = APIRouter(prefix="/api/v1/automation", tags=["automation"])


class ExtractFromURLRequest(BaseModel):
    """从 URL 提取字段请求"""
    url: str


class ExtractAllStepsRequest(BaseModel):
    """多步骤向导全步骤提取请求"""
    url: str
    max_steps: int = 10   # 最大遍历步数（防无限循环）


class MatchRequest(BaseModel):
    """字段匹配请求"""
    fields: List[Dict[str, Any]]
    use_llm: bool = True              # True=用 LLM 语义匹配；False=只用规则匹配（免费、快速）


class GenerateScriptRequest(BaseModel):
    """生成填写脚本请求"""
    fields: List[Dict[str, Any]]
    mappings: List[Dict[str, Any]]


class BossSearchRequest(BaseModel):
    """Boss 直聘岗位搜索请求"""
    keyword: str
    city: Optional[str] = None
    page: int = 1
    use_real: bool = True


class AutoFillRequest(BaseModel):
    """Playwright 自动填写请求"""
    url: str
    fields: List[Dict[str, Any]]
    mappings: List[Dict[str, Any]]
    headless: bool = True           # True=后台静默；False=弹出浏览器可视化
    auto_submit: bool = False       # 是否自动点击提交
    submit_selector: Optional[str] = None  # 提交按钮选择器


class OpenLoginRequest(BaseModel):
    """打开登录页请求"""
    site: str = "boss"              # 站点标识（boss / 暂只支持 boss）
    headless: bool = False          # 默认 headful，让用户看到浏览器


@router.post("/extract-from-url")
async def extract_from_url(
    request: ExtractFromURLRequest,
    user_id: str = Depends(get_current_user)
):
    """
    从 URL 提取表单字段（Web 版本，无需插件）

    流程：
    1. 用户输入目标 URL
    2. 系统后台抓取页面
    3. 自动识别表单字段
    4. 返回字段列表和页面信息（含多步骤向导结构检测）
    """
    logger.info(f"用户 {user_id} 请求从 URL 提取字段: {request.url}")

    try:
        # 使用智能填写服务抓取页面
        service = get_smart_fill_service()
        result = await service.extract_fields_from_url(request.url)

        # 如果检测到多步骤向导，附加提示
        wizard = result.get("wizard", {})
        if wizard.get("is_multi_step"):
            msg = (
                f"提取成功（检测到多步骤向导：当前第 {wizard.get('current_step', 0)} / "
                f"{wizard.get('total_steps', 0)} 步，可调用 /extract-all-steps 获取全部字段）"
            )
        else:
            msg = "提取成功"

        return ok(result, message=msg)

    except Exception as e:
        logger.error(f"字段提取失败: {e}")
        raise InternalServerError(f"字段提取失败: {e}")


@router.post("/extract-all-steps")
async def extract_all_steps(
    request: ExtractAllStepsRequest,
    user_id: str = Depends(get_current_user)
):
    """
    多步骤向导表单全步骤提取

    自动点击「下一步」遍历所有步骤，合并所有字段。
    适用于分步骤的招聘投递表单（如：基本信息 → 教育经历 → 工作经历 → 确认）。

    - 每个字段会附加 `step` 字段标记来源步骤
    - 返回 `steps` 数组含每步的截图和字段数
    - 达到 max_steps 或无「下一步」按钮时停止
    """
    logger.info(f"用户 {user_id} 请求多步骤提取: {request.url}, max_steps={request.max_steps}")

    if request.max_steps < 1 or request.max_steps > 20:
        raise BadRequestError("max_steps 必须在 1-20 之间")

    try:
        service = get_smart_fill_service()
        result = await service.extract_all_steps(
            url=request.url,
            max_steps=request.max_steps,
        )
        msg = (
            f"多步骤提取完成：共遍历 {result.get('total_steps_traversed', 0)} 步，"
            f"合并 {result.get('field_count', 0)} 个字段"
        )
        return ok(result, message=msg)
    except Exception as e:
        logger.error(f"多步骤提取失败: {e}", exc_info=True)
        raise InternalServerError(f"多步骤提取失败: {e}")


@router.post("/match")
async def match_fields(
    request: MatchRequest,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    字段语义匹配（基于用户画像）
    
    流程：
    1. 接收表单字段列表
    2. 从数据库加载用户画像
    3. 使用 LLM 进行语义匹配
    4. 返回匹配结果
    """
    logger.info(f"用户 {user_id} 请求字段匹配，字段数: {len(request.fields)}")
    
    try:
        # 从数据库加载用户画像
        profile = db.query(Profile).filter(Profile.user_id == user_id).first()
        if not profile:
            profile_data = {}
        else:
            profile_data = {
                "basic_info": profile.basic_info or {},
                "education": profile.education or [],
                "experience": profile.experience or [],
                "skills": profile.skills or [],
                "projects": profile.projects or [],
                "summary": profile.summary or {},
                "certifications": profile.certifications or [],
                "job_intent": profile.job_intent or {},
            }
        
        # 执行匹配
        matcher = FieldMatcher()
        result = await matcher.match(
            fields=request.fields,
            user_id=user_id,
            profile=profile_data,
            db=db,
            use_llm=request.use_llm,
        )

        return ok(
            {
                "mappings": result["mappings"],
                "profile_used": result["profile_used"],
                "source": result.get("source", "llm"),
            },
            message="匹配成功" if result.get("source") == "llm" else "规则匹配完成",
        )

    except Exception as e:
        logger.error(f"字段匹配失败: {e}")
        raise InternalServerError(f"字段匹配失败: {e}")


@router.post("/generate-script")
async def generate_fill_script(
    request: GenerateScriptRequest,
    user_id: str = Depends(get_current_user)
):
    """
    生成填写脚本（用户复制到浏览器控制台执行）
    
    流程：
    1. 接收字段列表和匹配结果
    2. 生成 JavaScript 填写脚本
    3. 用户复制到浏览器控制台执行
    """
    logger.info(f"用户 {user_id} 请求生成填写脚本")
    
    try:
        # 生成填写脚本
        script = _generate_fill_script(request.fields, request.mappings)
        
        return ok(
            {
                "script": script,
                "usage": "请将上述脚本复制到浏览器控制台（按 F12 打开）并执行"
            },
            message="脚本生成成功",
        )

    except Exception as e:
        logger.error(f"脚本生成失败: {e}")
        raise InternalServerError(f"脚本生成失败: {e}")


def _generate_fill_script(fields: List[Dict], mappings: List[Dict]) -> str:
    """
    生成填写脚本

    增强：
    - 支持 input / textarea / select / checkbox / radio / contenteditable
    - React/Vue 兼容（nativeInputValueSetter 触发 input 事件）
    - 自定义下拉（div + click 模拟）
    - 视觉反馈：填写成功高亮、失败字段标红
    - 多重选择器兜底（id → name → selector → aria-label）
    - 容错：单个字段失败不影响整体
    """
    # 合并字段元数据（field_id → field info）
    field_meta = {f.get("id") or f.get("name") or "": f for f in fields if f.get("id") or f.get("name")}

    # 构造填写数据数组（保留字段类型信息）
    fill_entries = []
    for mapping in mappings:
        fid = mapping.get("field_id") or mapping.get("id") or ""
        value = mapping.get("value")
        if not fid or value in (None, ""):
            continue
        meta = field_meta.get(fid, {})
        fill_entries.append({
            "id": fid,
            "value": str(value),
            "tag": (meta.get("tag") or "input").lower(),
            "type": (meta.get("type") or "text").lower(),
            "selector": meta.get("selector") or "",
            "label": meta.get("label") or fid,
            "options": meta.get("options") or [],
            "field_type_inferred": meta.get("field_type_inferred") or "",
        })

    # 转为 JSON 嵌入脚本（安全转义）
    fill_json = json.dumps(fill_entries, ensure_ascii=False)

    script = f"""// ============================================================
// OfferClaw 智能填写脚本（增强版）
// 支持：input/textarea/select/checkbox/radio/contenteditable
// 兼容：React / Vue / Angular 受控组件
// 反馈：成功高亮橄榄色，失败标红
// 用法：在目标页面按 F12 打开控制台，粘贴执行
// ============================================================
(function() {{
  'use strict';

  const FILL_DATA = {fill_json};

  // ---- 样式注入：视觉反馈 ----
  const style = document.createElement('style');
  style.textContent = `
    @keyframes oc-flash-ok {{
      0% {{ box-shadow: 0 0 0 0 rgba(107, 125, 10, 0.6); }}
      100% {{ box-shadow: 0 0 0 6px rgba(107, 125, 10, 0); }}
    }}
    @keyframes oc-flash-err {{
      0% {{ box-shadow: 0 0 0 0 rgba(185, 74, 58, 0.7); }}
      100% {{ box-shadow: 0 0 0 6px rgba(185, 74, 58, 0); }}
    }}
    .oc-filled {{ outline: 2px solid #6b7d0a !important; outline-offset: 1px; animation: oc-flash-ok 0.8s ease-out; }}
    .oc-failed {{ outline: 2px solid #b94a3a !important; outline-offset: 1px; animation: oc-flash-err 0.8s ease-out; }}
    .oc-badge {{
      position: absolute; right: -8px; top: -8px;
      background: #6b7d0a; color: #fff; font-size: 11px;
      width: 18px; height: 18px; border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      font-family: -apple-system, sans-serif; font-weight: bold;
      box-shadow: 0 2px 4px rgba(0,0,0,0.2); z-index: 99999;
    }}
  `;
  document.head.appendChild(style);

  // ---- 工具函数 ----
  function logOk(msg) {{ console.log('%c✓ ' + msg, 'color:#5a7a3a;font-weight:bold;'); }}
  function logWarn(msg) {{ console.warn('⚠️ ' + msg); }}
  function logErr(msg) {{ console.error('✗ ' + msg); }}

  // React/Vue 受控组件兼容：通过原生 setter 触发 input 事件
  function setNativeValue(el, value) {{
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype
                : el.tagName === 'SELECT' ? HTMLSelectElement.prototype
                : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value');
    if (setter && setter.set) {{
      setter.set.call(el, value);
    }} else {{
      el.value = value;
    }}
  }}

  // 多重选择器定位元素
  function findField(entry) {{
    // 1. 显式 selector
    if (entry.selector) {{
      try {{
        const el = document.querySelector(entry.selector);
        if (el) return el;
      }} catch (e) {{ /* 选择器语法错误，跳过 */ }}
    }}
    // 2. id
    if (entry.id) {{
      const el = document.getElementById(entry.id);
      if (el) return el;
      // 3. name
      const byName = document.querySelector(`[name="${{entry.id}}"]`);
      if (byName) return byName;
      // 4. aria-label
      const byAria = document.querySelector(`[aria-label="${{entry.label}}"]`);
      if (byAria) return byAria;
      // 5. placeholder
      const byPh = document.querySelector(`[placeholder="${{entry.label}}"]`);
      if (byPh) return byPh;
    }}
    // 6. label[for] 关联
    const labelEls = Array.from(document.querySelectorAll('label'));
    for (const l of labelEls) {{
      if (l.textContent.trim() === entry.label && l.htmlFor) {{
        const el = document.getElementById(l.htmlFor);
        if (el) return el;
      }}
    }}
    return null;
  }}

  // 标记视觉反馈
  function markOk(el) {{
    el.classList.add('oc-filled');
    // 添加角标
    if (getComputedStyle(el).position === 'static') el.style.position = 'relative';
    const badge = document.createElement('span');
    badge.className = 'oc-badge';
    badge.textContent = '✓';
    el.appendChild(badge);
    setTimeout(() => badge.remove(), 2000);
  }}
  function markFail(el) {{
    el.classList.add('oc-failed');
    setTimeout(() => el.classList.remove('oc-failed'), 1500);
  }}

  // ---- 按字段类型填写 ----
  function fillField(entry) {{
    const el = findField(entry);
    if (!el) {{
      logWarn(`未找到字段: ${{entry.label}} (${{entry.id}})`);
      return false;
    }}

    const tag = (el.tagName || '').toLowerCase();
    const type = (el.type || entry.type || 'text').toLowerCase();
    const val = entry.value;

    try {{
      // 1. contenteditable（富文本/自定义输入框）
      if (el.isContentEditable || el.getAttribute('contenteditable') === 'true') {{
        el.focus();
        el.innerText = val;
        el.dispatchEvent(new InputEvent('input', {{ bubbles: true, data: val }}));
        el.dispatchEvent(new Event('blur', {{ bubbles: true }}));
        markOk(el);
        logOk(`已填写(contenteditable): ${{entry.label}}`);
        return true;
      }}

      // 2. select（原生下拉）
      if (tag === 'select') {{
        let matched = false;
        // 精确 value 匹配
        for (const opt of el.options) {{
          if (opt.value === val || opt.text.trim() === val) {{
            setNativeValue(el, opt.value);
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            matched = true;
            break;
          }}
        }}
        // 模糊匹配
        if (!matched) {{
          for (const opt of el.options) {{
            if (opt.text.includes(val) || val.includes(opt.text.trim())) {{
              setNativeValue(el, opt.value);
              el.dispatchEvent(new Event('input', {{ bubbles: true }}));
              el.dispatchEvent(new Event('change', {{ bubbles: true }}));
              matched = true;
              break;
            }}
          }}
        }}
        if (matched) {{ markOk(el); logOk(`已填写(select): ${{entry.label}} = ${{val}}`); return true; }}
        logWarn(`select 无匹配选项: ${{entry.label}} (值=${{val}})`);
        markFail(el);
        return false;
      }}

      // 3. checkbox
      if (type === 'checkbox') {{
        const want = ['true', '1', 'yes', 'on', '✓', '是'].includes(val.toLowerCase());
        if (el.checked !== want) {{
          el.click();
        }}
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
        markOk(el);
        logOk(`已填写(checkbox): ${{entry.label}} = ${{want}}`);
        return true;
      }}

      // 4. radio - 选中匹配项
      if (type === 'radio') {{
        const group = document.querySelectorAll(`input[type="radio"][name="${{el.name}}"]`);
        let matched = false;
        for (const r of group) {{
          const rVal = (r.value || '').toLowerCase();
          const rLabel = (r.closest('label')?.textContent || r.getAttribute('aria-label') || '').trim().toLowerCase();
          if (rVal === val.toLowerCase() || rLabel === val.toLowerCase() || rLabel.includes(val.toLowerCase())) {{
            r.click();
            r.dispatchEvent(new Event('change', {{ bubbles: true }}));
            markOk(r);
            matched = true;
            break;
          }}
        }}
        if (matched) {{ logOk(`已填写(radio): ${{entry.label}} = ${{val}}`); return true; }}
        logWarn(`radio 无匹配项: ${{entry.label}} (值=${{val}})`);
        return false;
      }}

      // 5. 自定义下拉（div 模拟）：点击展开 → 点击选项
      if (el.getAttribute('role') === 'combobox' || el.classList.contains('ant-select-selector') ||
          el.classList.contains('el-select') || el.classList.contains('select-trigger')) {{
        el.click();
        // 等待下拉项出现并匹配
        setTimeout(() => {{
          const items = document.querySelectorAll('.ant-select-item, .el-select-dropdown__item, [role="option"], li[role="option"]');
          let matched = false;
          for (const it of items) {{
            if ((it.textContent || '').trim() === val || (it.textContent || '').includes(val)) {{
              it.click();
              markOk(el);
              logOk(`已填写(custom-select): ${{entry.label}} = ${{val}}`);
              matched = true;
              break;
            }}
          }}
          if (!matched) {{ logWarn(`自定义下拉无匹配: ${{entry.label}}`); markFail(el); }}
        }}, 200);
        return true;
      }}

      // 6. 文件上传（仅提示，无法自动填）
      if (type === 'file') {{
        logWarn(`文件字段需手动上传: ${{entry.label}} (建议值=${{val}})`);
        markFail(el);
        return false;
      }}

      // 7. 普通文本类 input / textarea（含 React/Vue 兼容）
      el.focus();
      setNativeValue(el, val);
      el.dispatchEvent(new Event('input', {{ bubbles: true }}));
      el.dispatchEvent(new Event('change', {{ bubbles: true }}));
      el.dispatchEvent(new Event('blur', {{ bubbles: true }}));
      markOk(el);
      logOk(`已填写(text): ${{entry.label}} = ${{val}}`);
      return true;

    }} catch (e) {{
      logErr(`填写失败: ${{entry.label}} - ${{e.message}}`);
      markFail(el);
      return false;
    }}
  }}

  // ---- 执行填写 ----
  console.log('%cOfferClaw 智能填写开始', 'background:#6b7d0a;color:#fff;padding:2px 8px;border-radius:3px;font-weight:bold;');
  console.log(`共 ${{FILL_DATA.length}} 个字段待填写`);

  let okCount = 0, failCount = 0;
  for (const entry of FILL_DATA) {{
    if (fillField(entry)) okCount++;
    else failCount++;
  }}

  console.log(`%c✓ 填写完成: 成功 ${{okCount}} / 失败 ${{failCount}}`, 'color:#6b7d0a;font-weight:bold;font-size:13px;');
  if (failCount > 0) {{
    console.log('%c提示: 失败字段可能是自定义组件，建议手动检查或调整 selector', 'color:#b8860b;');
  }}
}})();
"""
    return script


@router.post("/boss-search")
async def boss_search(
    request: BossSearchRequest,
    user_id: str = Depends(get_current_user)
):
    """
    搜索 Boss 直聘岗位

    - 优先真实抓取（Playwright，复用 userDataDir 登录态），失败降级为模拟数据
    - 检测到登录墙时返回 need_login=true，前端引导用户先登录
    - 检测到反爬/滑块时降级为模拟数据并提示
    - 返回结构化岗位列表，前端可一键创建投递记录
    """
    logger.info(
        f"用户 {user_id} 请求 Boss 搜索: keyword={request.keyword}, "
        f"city={request.city}, page={request.page}, use_real={request.use_real}"
    )

    if not request.keyword or not request.keyword.strip():
        raise BadRequestError("keyword 不能为空")

    try:
        service = get_boss_search_service()
        result = await service.search(
            keyword=request.keyword.strip(),
            city=request.city,
            page=request.page,
            use_real=request.use_real,
            user_id=user_id,
        )
        return ok(result, message=result.get("message", "搜索成功"))
    except Exception as e:
        logger.error(f"Boss 搜索失败: {e}", exc_info=True)
        raise InternalServerError(f"Boss 搜索失败: {e}")


@router.get("/login-status")
async def login_status(
    site: str = "boss",
    user_id: str = Depends(get_current_user),
):
    """
    检查指定站点的登录态（基于 userDataDir 持久化 cookie）

    返回：
        {
            "logged_in": bool,
            "login_url": str,
            "site": str,
            "message": str,
            "screenshot": Optional[str]
        }
    """
    logger.info(f"用户 {user_id} 检查 {site} 登录态")
    if site != "boss":
        raise BadRequestError(f"暂不支持站点 {site}，当前仅支持 boss")
    try:
        result = await check_boss_login(user_id=user_id)
        return ok(result, message=result["message"])
    except Exception as e:
        logger.error(f"登录态检查失败: {e}", exc_info=True)
        raise InternalServerError(str(e))


@router.post("/open-login")
async def open_login(
    request: OpenLoginRequest,
    user_id: str = Depends(get_current_user),
):
    """
    以 headful 模式打开登录页（让用户手动登录，登录态自动保存到 userDataDir）

    ⚠️ 此端点会阻塞最长 10 分钟，直到用户关闭浏览器窗口。
    前端应使用异步任务或后台任务调用，并提示用户「完成登录后请关闭浏览器窗口」。

    当前仅支持 boss 站点。
    """
    logger.info(f"用户 {user_id} 请求打开 {request.site} 登录页（headless={request.headless}）")
    if request.site != "boss":
        raise BadRequestError(f"暂不支持站点 {request.site}，当前仅支持 boss")
    try:
        # headless 参数当前未改变 open_boss_login 行为（登录需 headful 让用户操作），
        # 保留参数以兼容前端请求体，后续可扩展为 headless 模式下复用已登录态
        result = await open_boss_login(user_id=user_id)
        return ok(result, message=result["message"])
    except Exception as e:
        logger.error(f"打开登录页失败: {e}", exc_info=True)
        raise InternalServerError(str(e))


@router.post("/auto-fill")
async def auto_fill(
    request: AutoFillRequest,
    user_id: str = Depends(get_current_user),
):
    """
    Playwright 自动填写表单（后端启动浏览器，真正打开页面并填写）

    - 替代旧的「生成脚本让用户手动粘贴」模式
    - 支持 input/select/checkbox/radio/textarea/contenteditable/自定义下拉
    - React/Vue 受控组件兼容（nativeInputValueSetter）
    - 返回填写前/填写后截图，前端可视化展示
    - 默认不自动提交（auto_submit=False），让用户最后确认

    ⚠️ headless=False 时会弹出浏览器窗口（可视化模式），用户可观察填写过程
    """
    logger.info(
        f"用户 {user_id} 请求自动填表: url={request.url}, "
        f"fields={len(request.fields)}, mappings={len(request.mappings)}, "
        f"headless={request.headless}, auto_submit={request.auto_submit}"
    )
    if not request.url:
        raise BadRequestError("url 不能为空")
    try:
        service = get_auto_filler_service()
        result = await service.auto_fill(
            url=request.url,
            fields=request.fields,
            mappings=request.mappings,
            user_id=user_id,
            headless=request.headless,
            auto_submit=request.auto_submit,
            submit_selector=request.submit_selector,
        )
        return ok(result, message=result["message"])
    except Exception as e:
        logger.error(f"自动填表失败: {e}", exc_info=True)
        raise InternalServerError(f"自动填表失败: {e}")


@router.get("/status")
async def get_automation_status():
    """获取智能填写模块状态"""
    return ok(
        {
            "smart_fill": "available",
            "field_matcher": "available",
            "script_generator": "available",
            "boss_search": "available",
            "auto_filler": "available",
            "login_check": "available",
        },
        message="智能填写模块运行正常",
    )