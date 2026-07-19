"""
字段语义匹配器
使用 LLM 进行字段与用户画像的智能匹配
"""

import json
import logging
from typing import Optional
from sqlalchemy.orm import Session

logger = logging.getLogger("offerclaw.field_matcher")


class FieldMatcher:
    """字段语义匹配服务"""

    MATCH_PROMPT = """你是表单填写助手。给定表单字段列表和用户画像，输出 JSON 映射数组：
[{
  "field_id": "字段ID",
  "value": "填写值或 null",
  "confidence": 0.0-1.0,
  "source": "profile|local_sensitive|file_upload",
  "reason": "匹配理由(低置信度时必填)"
}]

规则:
- 下拉/单选：从 options 中选最匹配项的原文
- 文件字段：value 填 "FILE:resume"，source 填 "file_upload"
- 身份证/家庭住址等敏感字段：value 填 null，source 填 "local_sensitive"(扩展本地填值)
- 无法确定的字段：value 填 null，reason 说明原因

表单字段: {fields}
用户画像: {profile}"""

    async def match(self, fields: list, user_id: str, profile: dict,
                    llm_client=None, db: Optional[Session] = None) -> dict:
        """
        字段语义匹配

        Args:
            fields: 表单字段列表
            user_id: 用户 ID（用于订阅验证）
            profile: 用户画像数据
            llm_client: LLM 客户端（可选）
            db: 数据库 Session（可选）

        Returns:
            dict: {"mappings": [...], "profile_used": bool}
        """
        from app.core.llm import chat_json
        from app.core.subscription import SubscriptionManager

        # 1. 订阅校验（如果有数据库）
        if db:
            subscription_manager = SubscriptionManager(db)
            has_permission = subscription_manager.check_permission(user_id, 'autofill')
            if not has_permission:
                raise PermissionError("需要付费订阅才能使用智能匹配功能")

        # 2. LLM 语义匹配
        try:
            result = await chat_json(
                system="你是表单填写助手，只输出 JSON。",
                user=self.MATCH_PROMPT.format(
                    fields=json.dumps(fields, ensure_ascii=False, default=str),
                    profile=json.dumps(profile, ensure_ascii=False, default=str),
                ),
            )

            # 3. 计数（如果有数据库）
            if db:
                subscription_manager.increment_usage(user_id, 'autofill')

            mappings = result.get("mappings", result) if isinstance(result, dict) else result
            return {"mappings": mappings, "profile_used": True}

        except Exception as e:
            logger.error(f"LLM 匹配失败: {e}")
            # 降级：基于字段名简单匹配
            return await self._fallback_match(fields, profile)

    async def _fallback_match(self, fields: list, profile: dict) -> dict:
        """降级匹配策略（基于字段名）"""
        mappings = []

        # 常见字段名映射
        field_mapping = {
            'name': 'basic_info.name',
            'username': 'basic_info.name',
            'email': 'basic_info.email',
            'phone': 'basic_info.phone',
            'mobile': 'basic_info.phone',
            'gender': 'basic_info.gender',
            'city': 'job_intent.cities[0]',
        }

        for field in fields:
            field_id = field['id']
            field_label = field.get('label', '').lower()

            # 尝试匹配
            value = None
            for key, path in field_mapping.items():
                if key in field_id.lower() or key in field_label:
                    # 从 profile 提取值
                    value = self._extract_from_profile(profile, path)
                    if value:
                        break

            mappings.append({
                'field_id': field_id,
                'value': value,
                'confidence': 0.5 if value else 0.0,
                'source': 'profile' if value else None,
                'reason': None if value else '无法自动匹配'
            })

        return {"mappings": mappings, "profile_used": True}

    def _extract_from_profile(self, profile: dict, path: str):
        """从 profile 提取值"""
        try:
            parts = path.split('.')
            value = profile
            for part in parts:
                if '[' in part:
                    # 处理数组索引
                    key = part.split('[')[0]
                    index = int(part.split('[')[1].rstrip(']'))
                    value = value[key][index]
                else:
                    value = value[part]
            return value
        except:
            return None


# Dependency injection
def get_field_matcher():
    return FieldMatcher()