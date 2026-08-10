"""
日志工具：脱敏 + 结构化字段

求职场景下用户输入可能含手机号/微信号/薪资等敏感信息，
日志中不应记录原文，只记录长度和脱敏后的预览。
"""

import re
import logging
from typing import Any

# 敏感模式：手机号 / 邮箱 / 身份证 / 银行卡 / 微信号
_PHONE_RE = re.compile(r'1[3-9]\d{9}')
_EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
_IDCARD_RE = re.compile(r'\d{17}[\dXx]')
_BANKCARD_RE = re.compile(r'\d{16,19}')
# 薪资模式：25k / 25K / 25000 / 25k×16
_SALARY_RE = re.compile(r'\b\d{1,3}[kK]\b(?:[×x]\d{1,2})?|\b\d{4,6}\b(?:元/月)?')


def sanitize_for_log(text: str, max_len: int = 80) -> str:
    """脱敏用户输入用于日志记录

    策略：
    1. 截断到 max_len 字符
    2. 替换手机号/邮箱/身份证/银行卡为 ***
    """
    if not text:
        return ""
    text = str(text)
    # 截断
    if len(text) > max_len:
        text = text[:max_len] + "..."
    # 脱敏
    text = _PHONE_RE.sub("***", text)
    text = _EMAIL_RE.sub("***@***", text)
    text = _IDCARD_RE.sub("***", text)
    text = _BANKCARD_RE.sub("***", text)
    return text


class StructuredLoggerAdapter(logging.LoggerAdapter):
    """结构化日志适配器，附加 user_id / request_id 等字段"""

    def process(self, msg: str, kwargs: dict) -> tuple[str, dict]:
        extra = self.extra or {}
        prefix = " ".join(f"{k}={v}" for k, v in extra.items() if v is not None)
        if prefix:
            return f"[{prefix}] {msg}", kwargs
        return msg, kwargs


def get_logger(name: str, user_id: str | None = None, request_id: str | None = None) -> logging.LoggerAdapter:
    """获取带结构化字段的 logger"""
    extra = {"user_id": user_id, "request_id": request_id}
    return StructuredLoggerAdapter(logging.getLogger(name), extra)
