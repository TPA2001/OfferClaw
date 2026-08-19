"""
字段语义匹配器
使用 LLM 进行字段与用户画像的智能匹配，并提供基于规则的降级匹配。

降级匹配策略（无需 LLM 即可工作）：
- 中英文关键词识别（姓名 / 手机 / 邮箱 / 学校 / 专业 / 公司 / 职位 / 技能 / 自我评价 等）
- 支持画像扁平化字典的所有字段
- 支持 select / radio 字段的选项匹配
- 文件字段标记为 file_upload
- 敏感字段标记为 local_sensitive
"""

import json
import logging
import re
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

logger = logging.getLogger("offerclaw.field_matcher")


# ============================================================================
# 关键词字典（用于降级匹配）
# ============================================================================
# 每个表单字段通过 label/id/name 关键词匹配到一个或多个候选画像字段
# 优先级：精确匹配 > 包含匹配；按列表顺序尝试

KEYWORD_RULES: List[Dict[str, Any]] = [
    # ── 基本信息 ─────────────────────────────────────────────
    {
        "keys": ["name", "姓名", "真实姓名", "fullname", "your-name", "candidate_name"],
        "profile_field": "name",
        "confidence": 0.95,
        "category": "basic",
    },
    {
        "keys": ["phone", "mobile", "tel", "手机", "电话", "联系方式", "mobile_number", "phone_number"],
        "profile_field": "phone",
        "confidence": 0.95,
        "category": "basic",
    },
    {
        "keys": ["email", "邮箱", "电子邮件", "e-mail", "mail"],
        "profile_field": "email",
        "confidence": 0.95,
        "category": "basic",
    },
    {
        "keys": ["gender", "性别", "sex"],
        "profile_field": "gender",
        "confidence": 0.9,
        "category": "basic",
    },
    {
        "keys": ["birth", "birthday", "出生", "生日", "dob", "date_of_birth"],
        "profile_field": "birth",
        "confidence": 0.9,
        "category": "basic",
    },
    {
        "keys": ["age", "年龄", "岁数"],
        "profile_field": "_calc_age_from_birth",
        "confidence": 0.85,
        "category": "basic",
        "is_dynamic": True,
    },
    # ── 求职意向 ─────────────────────────────────────────────
    {
        "keys": ["position", "意向岗位", "目标岗位", "应聘岗位", "applied_position", "job_title", "expected_position", "期望职位", "应聘职位"],
        "profile_field": "intent_role",
        "confidence": 0.9,
        "category": "intent",
    },
    {
        "keys": ["city", "城市", "意向城市", "工作地点", "期望城市", "location", "工作城市", "expected_city"],
        "profile_field": "intent_cities",
        "confidence": 0.85,
        "category": "intent",
        "is_list": True,
    },
    {
        "keys": ["salary", "薪资", "期望薪资", "薪水", "待遇要求", "expected_salary"],
        "profile_field": "_build_salary_str",
        "confidence": 0.8,
        "category": "intent",
        "is_dynamic": True,
    },
    {
        "keys": ["salary_min", "薪资下限", "最低薪资"],
        "profile_field": "intent_salary_min",
        "confidence": 0.85,
        "category": "intent",
    },
    {
        "keys": ["salary_max", "薪资上限", "最高薪资"],
        "profile_field": "intent_salary_max",
        "confidence": 0.85,
        "category": "intent",
    },
    {
        "keys": ["job_type", "工作性质", "工作类型", "求职类型"],
        "profile_field": "intent_job_type",
        "confidence": 0.85,
        "category": "intent",
    },
    # ── 教育经历 ─────────────────────────────────────────────
    {
        "keys": ["school", "学校", "院校", "毕业院校", "university", "college", "graduated_school"],
        "profile_field": "latest_school",
        "confidence": 0.9,
        "category": "education",
    },
    {
        "keys": ["all_schools", "所有学校", "教育背景"],
        "profile_field": "all_schools",
        "confidence": 0.75,
        "category": "education",
    },
    {
        "keys": ["major", "专业", "所学专业", "specialty", "field_of_study"],
        "profile_field": "latest_major",
        "confidence": 0.9,
        "category": "education",
    },
    {
        "keys": ["degree", "学历", "学位", "education_background", "qualification", "最高学历"],
        "profile_field": "latest_degree",
        "confidence": 0.9,
        "category": "education",
    },
    {
        "keys": ["all_degrees", "所有学历"],
        "profile_field": "all_degrees",
        "confidence": 0.7,
        "category": "education",
    },
    # ── 工作经历 ─────────────────────────────────────────────
    {
        "keys": ["company", "公司", "所在公司", "雇主", "employer", "current_company", "最近公司"],
        "profile_field": "latest_company",
        "confidence": 0.9,
        "category": "experience",
    },
    {
        "keys": ["all_companies", "工作单位", "所有公司", "工作经历公司"],
        "profile_field": "all_companies",
        "confidence": 0.7,
        "category": "experience",
    },
    {
        "keys": ["title", "职位", "职务", "职称", "current_title", "job_title", "position_title", "最近职位"],
        "profile_field": "latest_title",
        "confidence": 0.9,
        "category": "experience",
    },
    {
        "keys": ["all_titles", "所有职位", "历任职位"],
        "profile_field": "all_titles",
        "confidence": 0.7,
        "category": "experience",
    },
    {
        "keys": ["exp_years", "工作年限", "工作经验", "years_of_experience", "work_years", "经验"],
        "profile_field": "total_exp_years",
        "confidence": 0.85,
        "category": "experience",
    },
    {
        "keys": ["exp_desc", "工作描述", "工作内容", "职责描述", "job_description", "responsibilities", "工作职责"],
        "profile_field": "latest_exp_desc",
        "confidence": 0.8,
        "category": "experience",
    },
    # ── 技能 ─────────────────────────────────────────────
    {
        "keys": ["skills", "技能", "技能标签", "技术栈", "tech_stack", "技术能力", "专长", "skill_tags"],
        "profile_field": "skills_str",
        "confidence": 0.85,
        "category": "skills",
    },
    # ── 项目经历 ─────────────────────────────────────────────
    {
        "keys": ["project", "项目", "项目经历", "项目名称", "project_name", "项目经验"],
        "profile_field": "latest_project",
        "confidence": 0.85,
        "category": "project",
    },
    {
        "keys": ["project_role", "项目角色", "项目职责"],
        "profile_field": "latest_project_role",
        "confidence": 0.8,
        "category": "project",
    },
    {
        "keys": ["project_desc", "项目描述", "项目介绍", "project_description"],
        "profile_field": "latest_project_desc",
        "confidence": 0.8,
        "category": "project",
    },
    {
        "keys": ["all_projects", "所有项目"],
        "profile_field": "all_projects",
        "confidence": 0.7,
        "category": "project",
    },
    # ── 自我评价 ─────────────────────────────────────────────
    {
        "keys": ["self_eval", "自我评价", "自我介绍", "个人简介", "personal_profile", "introduction", "about_me", "个人介绍"],
        "profile_field": "self_eval",
        "confidence": 0.85,
        "category": "summary",
    },
    {
        "keys": ["advantage", "个人优势", "优势", "核心竞争力", "亮点", "strengths"],
        "profile_field": "advantage",
        "confidence": 0.85,
        "category": "summary",
    },
    {
        "keys": ["career_goal", "职业目标", "职业规划", "发展规划", "career_plan"],
        "profile_field": "career_goal",
        "confidence": 0.85,
        "category": "summary",
    },
    # ── 证书 ─────────────────────────────────────────────
    {
        "keys": ["cert", "证书", "资格证书", "荣誉", "qualification", "certifications", "certificate"],
        "profile_field": "all_certs",
        "confidence": 0.8,
        "category": "cert",
    },
]


class FieldMatcher:
    """字段语义匹配服务"""

    MATCH_PROMPT = """你是表单填写助手。给定表单字段列表（含 current_value 页面已有值）和用户画像，输出 JSON 映射数组：
[{{
  "field_id": "字段ID",
  "value": "填写值或 null",
  "action": "keep|fill|correct|manual|skip",
  "confidence": 0.0-1.0,
  "source": "profile|local_sensitive|file_upload",
  "reason": "匹配理由(低置信度时必填)"
}}]

# 动作规划规则（核心）

每个字段必须给出 action，决策依据「页面已有值 current_value」与「画像值」的关系：

| action | 触发条件 | 含义 |
|---|---|---|
| `keep` | current_value 非空且看起来正确（尤其官网解析器已填的值），或画像无此字段但页面已有值 | 保留页面现有值，不填写 |
| `fill` | current_value 为空且画像有对应值 | 字段空白，用画像值填入 |
| `correct` | current_value 非空且与画像值强烈冲突 | 用画像值覆盖纠正 |
| `manual` | 敏感/模糊字段，需用户人工确认 | 标记人工，不自动填 |
| `skip` | 字段无关/不支持/无法推断 | 跳过 |

**重要：不要盲目覆盖。官网简历解析器已填的合理数据应 keep，只补填 blank 与纠正明显冲突。**

# 字段类型处理规则

- **文本类**（input/textarea）：直接填画像值
- **下拉/单选**（select/radio）：从 options 中选最匹配项的「value」原文；若无匹配则 value=null，action 视情况 keep 或 manual，reason 说明
- **复选框**（checkbox）：true/false/'是'/'否'，按画像语义判断
- **文件字段**（type=file 或 label 含「简历/附件/上传」）：value 填 "FILE:resume"，source 填 "file_upload"
- **contenteditable/富文本**：填画像对应字段的纯文本

# 敏感字段（不填值，标记 local_sensitive + manual）

- 身份证号、护照号、银行卡号、家庭住址、社保号
- value=null，source="local_sensitive"，action="manual"，reason 注明「敏感字段，本地填值」

# 置信度建议

- 0.95：字段标签与画像字段精确对应（如 "姓名" → name）
- 0.85：语义匹配但表述不同（如 "毕业院校" → latest_school）
- 0.70：模糊推断（如 "过往经历" → 工作描述）
- 0.50：select 选项无精确匹配但选了最接近的
- 0.00：完全无法匹配

# 注意事项

- 字段标签含「账号/用户名」时不要填真实姓名
- 「期望薪资」填 "20-40K" 格式（带单位）
- 列表型字段（如技能）用顿号「、」拼接
- 画像字段为空且 current_value 为空时 value=null，action="skip"，reason 注明「画像无此字段」
- current_value 非空且与画像值一致时 action="keep"，value 填 current_value

# 示例

## 示例 1：keep + fill + 文件上传
表单字段: [
  {{"id":"name","label":"姓名","type":"text","current_value":"张三"}},
  {{"id":"phone","label":"手机号","type":"tel","current_value":""}},
  {{"id":"resume","label":"上传简历","type":"file","current_value":""}}
]
用户画像: {{"name":"张三","phone":"13800000000"}}

输出:
[
  {{"field_id":"name","value":"张三","action":"keep","confidence":0.95,"source":"profile","reason":"页面已有值与画像一致"}},
  {{"field_id":"phone","value":"13800000000","action":"fill","confidence":0.95,"source":"profile","reason":"字段空白，填画像值"}},
  {{"field_id":"resume","value":"FILE:resume","action":"fill","confidence":0.9,"source":"file_upload","reason":null}}
]

## 示例 2：correct + 敏感 + 无匹配选项
表单字段: [
  {{"id":"id_card","label":"身份证号","type":"text","current_value":""}},
  {{"id":"school","label":"毕业院校","type":"text","current_value":"清华大学"}},
  {{"id":"degree","label":"学历","type":"select","current_value":"高中","options":[{{"value":"1","label":"高中"}},{{"value":"2","label":"本科"}}]}}
]
用户画像: {{"latest_school":"北京大学","latest_degree":"本科"}}

输出:
[
  {{"field_id":"id_card","value":null,"action":"manual","confidence":0.5,"source":"local_sensitive","reason":"敏感字段，本地填值"}},
  {{"field_id":"school","value":"北京大学","action":"correct","confidence":0.9,"source":"profile","reason":"页面值与画像冲突，纠正"}},
  {{"field_id":"degree","value":"2","action":"fill","confidence":0.9,"source":"profile","reason":"从选项中匹配 本科"}}
]

## 示例 3：skip
表单字段: [{{"id":"referral","label":"推荐人姓名","type":"text","current_value":""}}]
用户画像: {{"name":"张三"}}

输出:
[
  {{"field_id":"referral","value":null,"action":"skip","confidence":0.0,"source":null,"reason":"画像无推荐人信息"}}
]

# 实际任务

表单字段: {fields}
用户画像: {profile}"""

    async def match(self, fields: list, user_id: str, profile: dict,
                    llm_client=None, db: Optional[Session] = None,
                    use_llm: bool = True, skip_subscription: bool = False) -> dict:
        """
        字段语义匹配

        Args:
            fields: 表单字段列表
            user_id: 用户 ID（用于订阅验证）
            profile: 用户画像数据（嵌套结构 或 已扁平化的 dict）
            llm_client: LLM 客户端（可选）
            db: 数据库 Session（可选）
            use_llm: 是否使用 LLM（False 则仅用规则匹配）
            skip_subscription: 跳过订阅校验与计数（扩展端内测模式专用）

        Returns:
            dict: {"mappings": [...], "profile_used": bool, "source": "llm"|"rules"}
        """
        # 不用 LLM，直接规则匹配（避免加载 LLM 依赖）
        if not use_llm:
            return await self._fallback_match(fields, profile)

        from app.core.llm import get_gen_provider, Message
        from app.core.subscription import SubscriptionManager

        # 1. 订阅校验（如果有数据库；扩展端 skip_subscription 时跳过）
        if db and not skip_subscription:
            subscription_manager = SubscriptionManager(db)
            has_permission = subscription_manager.check_permission(user_id, 'autofill')
            if not has_permission:
                raise PermissionError("需要付费订阅才能使用智能匹配功能")

        # 2. LLM 语义匹配
        try:
            provider = get_gen_provider()
            messages = [
                Message(role="system", content="你是表单填写助手，只输出 JSON。"),
                Message(
                    role="user",
                    content=self.MATCH_PROMPT.format(
                        fields=json.dumps(fields, ensure_ascii=False, default=str),
                        profile=json.dumps(profile, ensure_ascii=False, default=str),
                    ),
                ),
            ]
            resp = await provider.chat(messages, temperature=0.2)
            raw = resp.content or ""

            # 解析 JSON（兼容 ```json``` 包裹与裸 JSON）
            json_text = raw.strip()
            if json_text.startswith("```"):
                json_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", json_text, flags=re.MULTILINE)
            match = re.search(r"\{[\s\S]*\}", json_text)
            if not match:
                raise ValueError("LLM 响应未包含 JSON 对象")
            result = json.loads(match.group())

            # 3. 计数（扩展端 skip_subscription 时跳过）
            if db and not skip_subscription:
                subscription_manager.increment_usage(user_id, 'autofill')

            mappings = result.get("mappings", result) if isinstance(result, dict) else result
            # 安全网：LLM 可能漏掉 action，按 current_value/value 兜底
            field_cv = {f.get("id") or f.get("name"): (f.get("current_value") or "") for f in fields if isinstance(f, dict)}
            for m in mappings:
                if isinstance(m, dict) and not m.get("action"):
                    fid = m.get("field_id") or m.get("id") or ""
                    m["action"] = self._decide_action(field_cv.get(fid, ""), m.get("value"))
            return {"mappings": mappings, "profile_used": True, "source": "llm"}

        except Exception as e:
            logger.error(f"LLM 匹配失败，降级到规则匹配: {e}")
            return await self._fallback_match(fields, profile)

    async def _fallback_match(self, fields: list, profile: dict) -> dict:
        """
        规则降级匹配（基于字段名关键词 + 画像数据）

        支持两种画像格式：
        - 嵌套结构（来自数据库）：{basic_info: {name: ...}, education: [...], ...}
        - 扁平化结构（来自 /profiles/flatten）：{name: ..., latest_school: ..., skills_str: ...}

        会自动检测并转换嵌套结构为扁平结构。
        输出每个字段的 action（keep/fill/correct/manual/skip），依据 current_value 与画像值关系。
        """
        # 自动转换嵌套结构为扁平结构
        flat = self._ensure_flatten(profile)

        mappings = []

        for field in fields:
            field_id = field.get("id") or field.get("name") or ""
            field_label = (field.get("label") or "").lower()
            field_name_lower = field_id.lower()
            field_type = (field.get("type") or "text").lower()
            options = field.get("options") or []
            current_value = (field.get("current_value") or "").strip()
            # 用于匹配的合并文本
            field_text = f"{field_id} {field_label} {field.get('name', '')} {field.get('placeholder', '')}".lower()

            # 文件上传字段
            if field_type == "file":
                mappings.append({
                    "field_id": field_id,
                    "value": "FILE:resume",
                    "action": "fill" if not current_value else "keep",
                    "confidence": 0.6,
                    "source": "file_upload",
                    "reason": "识别为文件上传字段",
                })
                continue

            # 身份证 / 家庭住址 等敏感字段
            if self._is_sensitive_field(field_text):
                mappings.append({
                    "field_id": field_id,
                    "value": None,
                    "action": "manual",
                    "confidence": 0.5,
                    "source": "local_sensitive",
                    "reason": "敏感字段，需本地填写",
                })
                continue

            # 按关键词规则匹配
            match = self._match_by_rules(field_text, flat)

            if match:
                value = match["value"]
                # 处理 select / radio：尝试从 options 中找最匹配的
                if options and value and field_type in ("select", "radio"):
                    matched_val = self._match_option(value, options)
                    if matched_val is not None:
                        value = matched_val
                        confidence = min(1.0, match["confidence"] + 0.05)
                    else:
                        # select 字段无匹配选项，置信度降低
                        confidence = match["confidence"] * 0.5
                        mappings.append({
                            "field_id": field_id,
                            "value": None,
                            "action": self._decide_action(current_value, None),
                            "confidence": confidence,
                            "source": "profile",
                            "reason": f"画像有值 '{match['value']}'，但选项无匹配",
                        })
                        continue
                else:
                    confidence = match["confidence"]

                mappings.append({
                    "field_id": field_id,
                    "value": value,
                    "action": self._decide_action(current_value, value),
                    "confidence": confidence,
                    "source": "profile",
                    "reason": None,
                })
            else:
                # 无匹配：保留页面已有值，否则跳过
                mappings.append({
                    "field_id": field_id,
                    "value": None,
                    "action": self._decide_action(current_value, None),
                    "confidence": 0.0,
                    "source": None,
                    "reason": "无法自动匹配",
                })

        return {"mappings": mappings, "profile_used": True, "source": "rules"}

    def _decide_action(self, current_value: str, value: Optional[str]) -> str:
        """
        依据页面已有值 current_value 与画像值 value 决定动作

        - 敏感字段由调用方先判定（不进这里）
        - 无 value（画像无值）：current_value 非空→keep，否则 skip
        - 有 value 且 current_value 空：fill
        - 两者都有：一致→keep，冲突→correct
        """
        cv = (current_value or "").strip()
        if not value:
            return "keep" if cv else "skip"
        if not cv:
            return "fill"
        # 双向包含视为一致（容错大小写/格式差异）
        if cv == value or value in cv or cv in value:
            return "keep"
        return "correct"

    def _ensure_flatten(self, profile: dict) -> dict:
        """
        确保画像是扁平化结构。
        如果是嵌套结构（含 basic_info/education/...），转换成扁平结构。
        """
        if not profile:
            return {}
        # 已经是扁平化（含 name 字段 或 latest_school 字段）
        if "name" in profile or "latest_school" in profile or "skills_str" in profile:
            return profile
        # 嵌套结构，转换
        flat: Dict[str, Any] = {}
        b = profile.get("basic_info") or {}
        flat["name"] = b.get("name", "")
        flat["phone"] = b.get("phone", "")
        flat["email"] = b.get("email", "")
        flat["gender"] = b.get("gender", "")
        flat["birth"] = b.get("birth", "")

        j = profile.get("job_intent") or {}
        flat["intent_role"] = j.get("role", "")
        flat["intent_cities"] = j.get("cities", [])
        flat["intent_salary_min"] = j.get("salary_min", "")
        flat["intent_salary_max"] = j.get("salary_max", "")
        flat["intent_job_type"] = j.get("job_type", "")

        edus = profile.get("education") or []
        if edus:
            latest = edus[-1]
            flat["latest_school"] = latest.get("school", "")
            flat["latest_major"] = latest.get("major", "")
            flat["latest_degree"] = latest.get("degree", "")
        flat["all_degrees"] = "、".join(filter(None, [e.get("degree", "") for e in edus]))
        flat["all_schools"] = "、".join(filter(None, [e.get("school", "") for e in edus]))

        exps = profile.get("experience") or []
        if exps:
            latest_exp = exps[-1]
            flat["latest_company"] = latest_exp.get("company", "")
            flat["latest_title"] = latest_exp.get("title", "")
            flat["latest_exp_desc"] = latest_exp.get("description", "")
        flat["all_companies"] = "、".join(filter(None, [e.get("company", "") for e in exps]))
        flat["all_titles"] = "、".join(filter(None, [e.get("title", "") for e in exps]))
        flat["total_exp_years"] = self._calc_exp_years(exps)

        skills = profile.get("skills") or []
        flat["skills"] = skills
        flat["skills_str"] = "、".join(skills)

        projs = profile.get("projects") or []
        if projs:
            latest_proj = projs[-1]
            flat["latest_project"] = latest_proj.get("name", "")
            flat["latest_project_role"] = latest_proj.get("role", "")
            flat["latest_project_desc"] = latest_proj.get("description", "")
        flat["all_projects"] = "、".join(filter(None, [p.get("name", "") for p in projs]))

        s = profile.get("summary") or {}
        flat["self_eval"] = s.get("self_eval", "")
        flat["advantage"] = s.get("advantage", "")
        flat["career_goal"] = s.get("career_goal", "")

        certs = profile.get("certifications") or []
        flat["all_certs"] = "、".join(filter(None, [c.get("name", "") for c in certs]))

        return flat

    def _match_by_rules(self, field_text: str, flat: dict) -> Optional[Dict[str, Any]]:
        """
        按 KEYWORD_RULES 顺序匹配，使用 rapidfuzz 模糊匹配

        匹配策略：
        - 短关键词（≤2 字符）用精确包含匹配，避免误命中（例如 "id" 不应匹配 "candidate"）
        - 长关键词用 WRatio 模糊匹配（阈值 82），同时保留精确包含的快速路径
        - 多个候选时取分数最高的
        """
        try:
            from rapidfuzz import fuzz
        except ImportError:
            fuzz = None

        candidates: List[tuple] = []  # [(score, rule, value), ...]

        for rule in KEYWORD_RULES:
            for key in rule["keys"]:
                key_lower = key.lower()
                # 1. 精确包含（仍是最可靠信号，得分 100）
                if key_lower in field_text:
                    score = 100.0
                elif fuzz is not None and len(key_lower) > 2:
                    # 2. 模糊匹配（仅对长关键词，避免 "id"/"sex" 等误匹配）
                    #    WRatio 对中英混合、长度差异都有较好容错
                    score = fuzz.WRatio(key_lower, field_text, score_cutoff=80)
                    if score < 82:
                        continue
                else:
                    continue

                profile_field = rule["profile_field"]
                value = self._extract_value(flat, profile_field, rule)
                if value:  # 画像中要有值才算匹配成功
                    candidates.append((score, rule, value, profile_field))

        if not candidates:
            return None

        # 取分数最高的；同分时保留原 KEYWORD_RULES 顺序（stable sort）
        candidates.sort(key=lambda x: -x[0])
        best_score, best_rule, best_value, best_field = candidates[0]
        # 置信度：基础置信度 × 模糊分数比例，但不超过规则定义的 confidence
        adjusted_conf = min(best_rule["confidence"], best_rule["confidence"] * (best_score / 100.0) + 0.1)
        return {
            "value": best_value,
            "confidence": round(adjusted_conf, 3),
            "category": best_rule["category"],
            "profile_field": best_field,
        }

    def _extract_value(self, flat: dict, profile_field: str, rule: Dict) -> Any:
        """从扁平化画像中提取值，支持动态字段"""
        # 动态计算字段
        if rule.get("is_dynamic"):
            if profile_field == "_calc_age_from_birth":
                return self._calc_age(flat.get("birth", ""))
            if profile_field == "_build_salary_str":
                smin = flat.get("intent_salary_min")
                smax = flat.get("intent_salary_max")
                if smin and smax:
                    return f"{smin}-{smax}K"
                if smin:
                    return f"{smin}K 以上"
                if smax:
                    return f"{smax}K 以内"
                return ""

        value = flat.get(profile_field, "")
        # 列表型字段：取第一个或拼接
        if rule.get("is_list") and isinstance(value, list):
            return value[0] if value else ""
        # 列表型字段（如 skills_str 已是字符串）
        if isinstance(value, list):
            return "、".join(str(v) for v in value) if value else ""
        # 数值型转字符串
        if value in (0, False):
            return str(value) if value == 0 else ""
        return value if value else ""

    def _calc_age(self, birth: str) -> str:
        """从出生日期计算年龄"""
        if not birth:
            return ""
        try:
            from datetime import datetime
            # 兼容 YYYY-MM 和 YYYY-MM-DD
            m = re.match(r"(\d{4})-(\d{1,2})", birth)
            if not m:
                return ""
            birth_year, birth_month = int(m.group(1)), int(m.group(2))
            now = datetime.now()
            age = now.year - birth_year
            if now.month < birth_month:
                age -= 1
            return str(age) if age > 0 else ""
        except Exception:
            return ""

    def _calc_exp_years(self, exps: list) -> str:
        """根据工作经历的起止时间估算工作年限"""
        if not exps:
            return ""
        from datetime import datetime
        total_months = 0
        for e in exps:
            start = e.get("start_date", "")
            end = e.get("end_date", "")
            if not start:
                continue
            try:
                m = re.match(r"(\d{4})-(\d{1,2})", start)
                if not m:
                    continue
                sy, sm = int(m.group(1)), int(m.group(2))
                if end and end != "至今":
                    m2 = re.match(r"(\d{4})-(\d{1,2})", end)
                    if not m2:
                        continue
                    ey, em = int(m2.group(1)), int(m2.group(2))
                else:
                    now = datetime.now()
                    ey, em = now.year, now.month
                months = (ey - sy) * 12 + (em - sm)
                if months > 0:
                    total_months += months
            except Exception:
                continue
        years = total_months / 12
        if years >= 1:
            return f"{years:.1f}年"
        if total_months > 0:
            return f"{total_months}个月"
        return ""

    def _is_sensitive_field(self, field_text: str) -> bool:
        """
        判断是否为敏感字段（身份证 / 家庭住址 / 银行卡等）

        匹配策略：
        - 精确包含优先（"身份证" in field_text）
        - 模糊匹配兜底（rapidfuzz WRatio ≥ 85），用于捕捉 "身份证据" 等 OCR/拼写变体
        - 短关键词（≤3 字符）仅用精确包含，避免误判
        """
        sensitive_keys = [
            "id_number", "id_card", "身份证", "身份号", "身份证明",
            "home_address", "住址", "家庭住址", "地址",
            "bank_card", "银行卡", "银行账号",
            "idcard", "identity",
        ]
        # 1. 精确包含
        if any(k in field_text for k in sensitive_keys):
            return True
        # 2. 模糊匹配兜底
        try:
            from rapidfuzz import fuzz
        except ImportError:
            return False
        for k in sensitive_keys:
            if len(k) <= 3:
                continue
            if fuzz.WRatio(k, field_text, score_cutoff=85) >= 85:
                return True
        return False

    def _match_option(self, value: str, options: list) -> Optional[str]:
        """
        从 select/radio 的选项中找最匹配的

        匹配策略（按优先级）：
        1. 精确匹配（value 或 label 完全相等）
        2. 包含匹配（双向 substring）
        3. 模糊匹配（rapidfuzz WRatio ≥ 82），用于捕捉 "本科/学士" 等同义变体
        """
        if not value:
            return None
        value_lower = str(value).lower().strip()
        # 1. 精确匹配
        for opt in options:
            opt_val = str(opt.get("value", "")).strip()
            opt_label = str(opt.get("label", opt.get("text", ""))).strip()
            if opt_val == value or opt_label == value:
                return opt_val or opt_label
        # 2. 包含匹配（双向）
        for opt in options:
            opt_val = str(opt.get("value", "")).strip()
            opt_label = str(opt.get("label", opt.get("text", ""))).strip()
            if value_lower in opt_val.lower() or value_lower in opt_label.lower():
                return opt_val or opt_label
            if opt_val.lower() in value_lower or opt_label.lower() in value_lower:
                return opt_val or opt_label
        # 3. 模糊匹配兜底
        try:
            from rapidfuzz import fuzz, process
        except ImportError:
            return None
        opt_strs = []
        opt_map = {}  # (val,label) -> return value
        for opt in options:
            opt_val = str(opt.get("value", "")).strip()
            opt_label = str(opt.get("label", opt.get("text", ""))).strip()
            for s in (opt_val, opt_label):
                if s:
                    opt_strs.append(s)
                    opt_map[s] = opt_val or opt_label
        if not opt_strs:
            return None
        best = process.extractOne(value, opt_strs, scorer=fuzz.WRatio, score_cutoff=82)
        if best:
            matched_str = best[0]
            return opt_map.get(matched_str)
        return None

    def _extract_from_profile(self, profile: dict, path: str):
        """从 profile 提取值（保留兼容旧调用）"""
        try:
            parts = path.split('.')
            value = profile
            for part in parts:
                if '[' in part:
                    key = part.split('[')[0]
                    index = int(part.split('[')[1].rstrip(']'))
                    value = value[key][index]
                else:
                    value = value[part]
            return value
        except (KeyError, IndexError, TypeError, ValueError) as e:
            logger.debug(f"按路径提取字段值失败: {e}")
            return None


# Dependency injection
def get_field_matcher():
    return FieldMatcher()
