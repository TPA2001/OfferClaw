"""
画像敏感字段清洗器

统一供 REST API（app/api/profile.py）与 Agent 工具（app/agent/tools/profile_tools.py）
使用，确保身份证号、家庭住址、银行卡、护照、社保、紧急联系人等敏感 PII
在任何写入路径下都不会被持久化到后端数据库。
"""

# 敏感字段关键词（大小写不敏感，按 substring 匹配 key 名）
SENSITIVE_PROFILE_KEYS = [
    # 身份证
    "id_card", "idcard", "id_number", "identity", "身份证", "身份号", "身份证明",
    # 住址
    "home_address", "address", "住址", "家庭住址", "户籍地址",
    # 银行卡
    "bank_card", "bank_account", "银行卡", "银行账号",
    # 护照
    "passport", "护照",
    # 社保
    "social_security", "社保", "社保号",
    # 紧急联系人（本地专属）
    "emergency_contact", "emergency_phone", "紧急联系人", "紧急电话",
]


def strip_sensitive_basic(basic_info):
    """剔除 basic_info 中可能混入的敏感字段，返回清洗后的 dict。

    即便前端误传、或 LLM Agent 把敏感值带过来，也一律丢弃。
    非 dict 输入原样返回。
    """
    if not isinstance(basic_info, dict):
        return basic_info
    cleaned = {}
    for k, v in basic_info.items():
        kl = str(k).lower()
        if any(s in kl for s in SENSITIVE_PROFILE_KEYS):
            continue
        cleaned[k] = v
    return cleaned
