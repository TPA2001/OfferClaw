"""扩展端隐私脱敏模块

目标:当扩展走 LLM 增强匹配时,确保 PII(姓名/手机/邮箱/出生)不离开本地到第三方 LLM。
策略:
1. redact_flat_profile —— 把扁平化画像里的 PII 值替换为占位符,记录 token→真实值 映射
2. redact_fields       —— 把表单字段 current_value 里疑似 PII 的值替换为占位符
3. restore_mappings    —— LLM 返回的 value 若为占位符,还原为真实值

说明:
- 规则匹配模式(use_llm=false)完全不调 LLM,profile 仅在后端内存处理,天然零泄露。
- LLM 模式仅发送脱敏后的画像/字段给 LLM,LLM 只看到占位符。
- 敏感字段(身份证/住址/银行卡)后端 profile 本就不存储,由 FieldMatcher 标记
  source=local_sensitive,扩展从本地 storage 读取填写。
"""
import re
from typing import Any, Dict, List, Tuple

# 需脱敏的 PII 字段(key in flat profile → 占位符 token)
PII_TOKENS: Dict[str, str] = {
    "name": "[REDACTED_NAME]",
    "phone": "[REDACTED_PHONE]",
    "email": "[REDACTED_EMAIL]",
    "birth": "[REDACTED_BIRTH]",
}

# 用于识别 current_value 中 PII 的正则(手机号 / 邮箱 / 身份证)
PHONE_RE = re.compile(r"1[3-9]\d{9}")
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
ID_CARD_RE = re.compile(r"\d{17}[\dXx]|\d{15}")


def redact_flat_profile(flat: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """把扁平化画像的 PII 字段替换为占位符

    Returns:
        (redacted_flat, token_map)
        - redacted_flat: 脱敏后的画像(可安全发给 LLM)
        - token_map: {占位符: 真实值} 用于后续还原
    """
    redacted = dict(flat)
    token_map: Dict[str, Any] = {}
    for field, token in PII_TOKENS.items():
        val = flat.get(field)
        if val:
            redacted[field] = token
            token_map[token] = val
    return redacted, token_map


def redact_fields(fields: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """把表单字段 current_value 里疑似 PII 的值替换为占位符

    网申表单可能预填了用户信息(如姓名/手机),current_value 含真实 PII。
    脱敏后 LLM 仍能判断"非空→倾向 keep",但看不到真实值。

    Returns:
        (redacted_fields, value_map)
        - redacted_fields: 脱敏后的字段列表
        - value_map: {占位符: 真实值}
    """
    value_map: Dict[str, str] = {}
    redacted: List[Dict[str, Any]] = []
    for f in fields:
        nf = dict(f)
        cv = f.get("current_value") or ""
        if isinstance(cv, str) and cv:
            placeholder = None
            if PHONE_RE.search(cv):
                placeholder = "[REDACTED_PHONE]"
            elif EMAIL_RE.search(cv):
                placeholder = "[REDACTED_EMAIL]"
            elif ID_CARD_RE.search(cv):
                placeholder = "[REDACTED_ID]"
            if placeholder:
                token = f"{placeholder}_{id(nf) & 0xffff}"
                value_map[token] = cv
                # 必须写入带后缀的 token，restore_mappings 才能按 value_map 命中还原
                nf["current_value"] = token
        redacted.append(nf)
    return redacted, value_map


def restore_mappings(mappings: List[Dict[str, Any]],
                     token_map: Dict[str, Any],
                     value_map: Dict[str, str]) -> List[Dict[str, Any]]:
    """把 LLM 返回 mappings 里的占位符 value 还原为真实值

    - token_map: 画像 PII 占位符 → 真实值
    - value_map: current_value 占位符 → 真实值(还原 current_value 用于展示)
    """
    for m in mappings:
        if not isinstance(m, dict):
            continue
        v = m.get("value")
        if isinstance(v, str):
            # 还原画像 PII 占位符
            if v in token_map:
                m["value"] = token_map[v]
            # 还原表单 current_value 占位符（LLM 可能把页面预填值回写为 value）
            elif v in value_map:
                m["value"] = value_map[v]
        # 还原 current_value 字段(供扩展展示页面原值)
        cv = m.get("current_value")
        if isinstance(cv, str) and cv in value_map:
            m["current_value"] = value_map[cv]
    return mappings
