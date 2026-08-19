"""简历 PDF 解析模块

从 PDF 简历提取文本 → 结构化为 OfferClaw 画像 JSON。

隐私与降级策略：
- 文本提取用 pdfplumber（本地，非 LLM）
- 结构化优先 LLM（用户已配置 Key 时），LLM 看到的是用户主动上传的自己的简历，用于填充自己的画像
- LLM 未配置或失败时降级规则解析（正则 + 关键词），零外部依赖、零隐私泄露
- 敏感字段（身份证/住址）后端 profile 本就不存储，解析结果也不含这些
"""
import io
import json
import logging
import re
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


# OfferClaw 画像空结构（与前端 profile.js emptyProfile 对齐）
def empty_profile() -> Dict[str, Any]:
    return {
        "basic": {"name": "", "gender": "", "age": "", "phone": "", "email": "",
                  "location": "", "avatar": "", "job_intent": ""},
        "education": [],
        "experience": [],
        "projects": [],
        "skills": [],
        "summary": {"self_intro": "", "strengths": "", "career_goal": "",
                    "expected_salary": "", "expected_location": "", "expected_position": ""},
        "certificates": [],
        "job_intent": {"target_positions": [], "target_cities": [], "expected_salary": "",
                       "work_type": "", "availability": ""},
    }


RESUME_PARSE_PROMPT = """你是简历解析助手。从下方简历文本中提取结构化信息，严格返回 JSON（不要 markdown 代码块、不要任何解释文字）。

字段结构如下：
{
  "basic": {"name": "", "gender": "", "age": "", "phone": "", "email": "", "location": "", "job_intent": ""},
  "education": [{"school": "", "degree": "", "major": "", "start_date": "", "end_date": "", "gpa": "", "description": ""}],
  "experience": [{"company": "", "position": "", "start_date": "", "end_date": "", "description": "", "achievements": []}],
  "projects": [{"name": "", "role": "", "description": "", "start_date": "", "end_date": "", "tech_stack": []}],
  "skills": [{"name": "", "level": "熟悉", "category": ""}],
  "summary": {"self_intro": "", "strengths": "", "career_goal": "", "expected_salary": "", "expected_position": ""},
  "certificates": [{"name": "", "issuer": "", "date": "", "score": ""}],
  "job_intent": {"target_positions": [], "target_cities": [], "expected_salary": "", "work_type": ""}
}

规则：
- 无法确定的字段留空字符串或空数组，不要编造
- tech_stack / achievements / target_positions / target_cities 用字符串数组
- skills 为对象数组，name 必填，level 默认"熟悉"，category 可空（编程语言/框架/工具/软技能）
- 日期统一 YYYY-MM 或 YYYY-MM-DD
- degree 取：高中/大专/本科/硕士/博士
- gender 取：男/女
- 只返回 JSON 对象本身

简历文本：
{resume_text}"""


def extract_text(pdf_bytes: bytes) -> str:
    """用 pdfplumber 提取 PDF 全文文本"""
    import pdfplumber

    parts = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            if t:
                parts.append(t)
    return "\n".join(parts)


# ============ 规则降级解析（无 LLM 时使用） ============

_PHONE_RE = re.compile(r"1[3-9]\d{9}")
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_DATE_RE = re.compile(r"(20\d{2})\s*[-/.年]\s*(\d{1,2})(?:\s*[-/.–~至]\s*(20\d{2})\s*[-/.年]\s*(\d{1,2}))?")
_CN_NAME_RE = re.compile(r"^[\u4e00-\u9fa5]{2,4}$")
# PDF 字体未正确映射时出现的 CID 占位符（如 "(cid:105)"），属于噪声
_CID_RE = re.compile(r"\(cid:\d+\)")

SCHOOL_HINTS = ["大学", "学院", "University", "university", "College", "college", "研究院", "研究所", "School"]
DEGREE_KEYWORDS = ["博士", "硕士", "本科", "大专", "专科", "PhD", "Master", "MBA", "Bachelor"]
DEGREE_NORMALIZE = {"博士": "博士", "PhD": "博士", "Doctor": "博士",
                    "硕士": "硕士", "Master": "硕士", "MBA": "硕士",
                    "本科": "本科", "Bachelor": "本科", "学士": "本科",
                    "大专": "大专", "专科": "大专", "Associate": "大专"}
COMPANY_HINTS = ["有限公司", "股份公司", "集团", "科技", "网络", "实验室", "工作室", "Inc", "Ltd", "Co."]
SKILL_LIB = ["Python", "Java", "C++", "C语言", "Go", "Rust", "JavaScript", "TypeScript",
             "React", "Vue", "Node", "Angular", "FastAPI", "Django", "Flask", "Spring",
             "MySQL", "Redis", "PostgreSQL", "MongoDB", "Elasticsearch", "Kafka", "RabbitMQ",
             "Docker", "Kubernetes", "Linux", "Git", "Hadoop", "Spark", "Flink",
             "PyTorch", "TensorFlow", "LangChain", "LangGraph", "Milvus", "BM25",
             "vLLM", "LoRA", "GPTQ", "CUDA", "KVCache", "PagedAttention",
             "CNN", "RNN", "Transformer", "Attention", "LLM", "RAG",
             "机器学习", "深度学习", "NLP", "CV", "AI"]
SKILL_LEVEL_HINTS = {"精通": "精通", "掌握": "掌握", "熟悉": "熟悉", "熟练": "熟悉", "了解": "了解"}

# 按技能名归类的标准类别（兜底为空字符串，由 bullet 行内容再推断）
SKILL_CATEGORY_MAP = {
    # 编程语言
    "Python": "编程语言", "Java": "编程语言", "C++": "编程语言", "C语言": "编程语言",
    "Go": "编程语言", "Rust": "编程语言", "JavaScript": "编程语言", "TypeScript": "编程语言",
    # 框架
    "React": "框架", "Vue": "框架", "Node": "框架", "Angular": "框架",
    "FastAPI": "框架", "Django": "框架", "Flask": "框架", "Spring": "框架",
    "LangChain": "框架", "LangGraph": "框架",
    # 存储/中间件
    "MySQL": "中间件", "Redis": "中间件", "PostgreSQL": "中间件", "MongoDB": "中间件",
    "Elasticsearch": "中间件", "Kafka": "中间件", "RabbitMQ": "中间件", "Milvus": "中间件", "BM25": "中间件",
    # 工具/运维
    "Docker": "工具", "Kubernetes": "工具", "Linux": "工具", "Git": "工具",
    "Hadoop": "工具", "Spark": "工具", "Flink": "工具",
    # AI/ML
    "PyTorch": "AI/ML", "TensorFlow": "AI/ML", "CNN": "AI/ML", "RNN": "AI/ML",
    "Transformer": "AI/ML", "Attention": "AI/ML", "LLM": "AI/ML", "RAG": "AI/ML",
    "机器学习": "AI/ML", "深度学习": "AI/ML", "NLP": "AI/ML", "CV": "AI/ML",
    "vLLM": "AI/ML", "LoRA": "AI/ML", "GPTQ": "AI/ML", "CUDA": "AI/ML",
    "KVCache": "AI/ML", "PagedAttention": "AI/ML", "AI": "AI/ML",
}

# 简历常见分区标题（按出现优先级；用于切片）
SECTION_HEADERS = [
    ("education", ["教育经历", "教育背景", "学历", "Education"]),
    ("experience", ["工作经历", "实习经历", "工作经验", "实习经验", "Work Experience", "Internship"]),
    ("projects", ["项目经历", "项目经验", "Projects", "项目"]),
    ("skills", ["专业技能", "技能", "技术栈", "Skills"]),
    ("certificates", ["证书", "资格证书", "Certifications"]),
    ("summary", ["自我评价", "个人简介", "自我介绍", "Summary", "Profile"]),
    ("job_intent", ["求职意向", "期望工作", "Job Intention"]),
    ("honors", ["荣誉", "奖项", "科研", "Honors"]),
]


def _strip_cid(text: str) -> str:
    """去除 PDF 字体未映射产生的 (cid:xxx) 噪声"""
    return _CID_RE.sub("", text)


def _split_sections(lines: List[str]) -> Dict[str, List[str]]:
    """按区段标题切分简历行，返回 {section_key: [lines]}"""
    sections: Dict[str, List[str]] = {"__head__": [], **{k: [] for k, _ in SECTION_HEADERS}}
    current = "__head__"
    for line in lines:
        switched = False
        for key, headers in SECTION_HEADERS:
            if any(h in line for h in headers) and len(line) <= 20:
                current = key
                switched = True
                break
        if switched:
            continue
        sections[current].append(line)
    return sections


def _parse_dates(text: str) -> Tuple[str, str]:
    """从文本提取起止日期 (start, end)；end 未匹配时为空字符串，'至今'类视为空字符串但记为'至今'"""
    m = _DATE_RE.search(text)
    if not m:
        return ("", "")
    sy, sm = m.group(1), m.group(2)
    start = f"{sy}-{sm.zfill(2)}"
    ey, em = m.group(3), m.group(4)
    if ey and em:
        return (start, f"{ey}-{em.zfill(2)}")
    # 单日期：检查是否含"至今"
    if "至今" in text or "现在" in text or "Present" in text:
        return (start, "至今")
    return (start, "")


def _parse_basic(head_lines: List[str], profile: Dict[str, Any]) -> None:
    """从头几行解析基本信息：姓名/性别/年龄/籍贯/手机/邮箱/求职方向"""
    if not head_lines:
        return
    full = "\n".join(head_lines)

    # 姓名：第一个 2-4 字纯中文行（排除含手机/邮箱/数字的行）
    for line in head_lines[:6]:
        cleaned = _strip_cid(line).strip()
        if _PHONE_RE.search(cleaned) or _EMAIL_RE.search(cleaned):
            continue
        # 去掉分隔后的纯净行
        if _CN_NAME_RE.match(cleaned):
            profile["basic"]["name"] = cleaned
            break

    # 手机/邮箱（全文）
    m = _PHONE_RE.search(full)
    if m:
        profile["basic"]["phone"] = m.group()
    m = _EMAIL_RE.search(full)
    if m:
        profile["basic"]["email"] = m.group()

    # 性别 + 年龄 + 籍贯（常在同一行）
    for line in head_lines[:8]:
        cleaned = _strip_cid(line)
        if "男" in cleaned and "性别" in cleaned or ("男" in cleaned and ("岁" in cleaned or "籍贯" in cleaned)):
            profile["basic"]["gender"] = "男"
        elif "女" in cleaned and "性别" in cleaned or ("女" in cleaned and ("岁" in cleaned or "籍贯" in cleaned)):
            profile["basic"]["gender"] = "女"
        m = re.search(r"(\d{2})\s*岁", cleaned)
        if m and not profile["basic"]["age"]:
            profile["basic"]["age"] = m.group(1)
        m = re.search(r"籍贯[:：\s]*([^\s]+)", cleaned)
        if m and not profile["basic"]["location"]:
            profile["basic"]["location"] = m.group(1)

    # 求职方向（第二行常见的"AIAgent/LLM应用开发"等）
    if len(head_lines) >= 2:
        line2 = _strip_cid(head_lines[1]).strip()
        # 排除明显的 PII 行
        if line2 and not _PHONE_RE.search(line2) and not _EMAIL_RE.search(line2):
            # 简短标题行（不超过 30 字）
            if len(line2) <= 30 and not any(h in line2 for h in SCHOOL_HINTS):
                profile["basic"]["job_intent"] = line2


def _parse_education(lines: List[str], profile: Dict[str, Any]) -> None:
    """解析教育经历：'学校 学院，专业，学位 起止日期' 格式"""
    for line in lines:
        cleaned = _strip_cid(line).strip()
        if not cleaned:
            continue
        if not any(h in cleaned for h in SCHOOL_HINTS):
            continue
        # 跳过荣誉/奖项等行（含"奖""学金"等但不含日期）
        if ("奖学金" in cleaned or "荣誉" in cleaned or "奖" in cleaned) and not _DATE_RE.search(cleaned):
            continue

        # 提取日期
        start, end = _parse_dates(cleaned)
        # 去除日期部分，剩下"学校 学院，专业，学位"
        body = _DATE_RE.sub("", cleaned).strip(" -–—,，")
        # 去掉括号备注（如 (211)）
        body = re.sub(r"[\(（][^\)）]*[\)）]", "", body).strip()

        # 学位
        degree = ""
        for kw, deg in DEGREE_NORMALIZE.items():
            if kw in body:
                degree = deg
                break

        # 用逗号/空格分割字段
        parts = [p.strip() for p in re.split(r"[，,\s]+", body) if p.strip()]
        school = ""
        major = ""
        for p in parts:
            if any(h in p for h in SCHOOL_HINTS) and not school:
                school = (school + " " + p).strip() if school else p
            elif p in DEGREE_KEYWORDS or p in DEGREE_NORMALIZE:
                continue  # 学位已单独提取
            elif not major:
                major = p
            else:
                major = (major + " " + p).strip()

        # 兜底：若没拆出学校，整行去括号去日期作为学校名
        if not school:
            school = body

        profile["education"].append({
            "school": school, "degree": degree, "major": major,
            "start_date": start, "end_date": end, "gpa": "", "description": ""
        })


def _parse_experience(lines: List[str], profile: Dict[str, Any]) -> None:
    """解析工作/实习经历：'公司 职位 起止日期' 格式，后续非空行作为描述"""
    i = 0
    while i < len(lines):
        cleaned = _strip_cid(lines[i]).strip()
        if not cleaned or cleaned.startswith("•") or cleaned.startswith("-"):
            i += 1
            continue
        # 含公司关键词或含日期+职位，且不是项目名/技能行
        has_company = any(h in cleaned for h in COMPANY_HINTS)
        has_date = bool(_DATE_RE.search(cleaned))
        if not (has_company or has_date) or any(h in cleaned for h in SCHOOL_HINTS):
            i += 1
            continue

        start, end = _parse_dates(cleaned)
        body = _DATE_RE.sub("", cleaned).strip(" -–—,，")

        # 拆公司 + 职位：公司在前(含公司关键词)，剩余为职位
        company = ""
        position = ""
        parts = re.split(r"[\s]+", body, maxsplit=1)
        if len(parts) >= 2:
            # 找含公司关键词的部分
            if any(h in parts[0] for h in COMPANY_HINTS):
                company = parts[0]
                position = parts[1]
            elif any(h in parts[1] for h in COMPANY_HINTS):
                company = parts[1]
                position = parts[0]
            else:
                company = parts[0]
                position = parts[1]
        else:
            company = body

        # 收集后续描述：本条目后续所有非"新条目"行
        desc_lines = []
        j = i + 1
        while j < len(lines):
            nxt = _strip_cid(lines[j]).strip()
            if not nxt:
                j += 1
                continue
            # 遇到下一个"公司 + 日期"组合的新条目，停止
            if any(h in nxt for h in COMPANY_HINTS) and _DATE_RE.search(nxt):
                break
            # bullet 行 + 普通描述行 都纳入描述
            desc_lines.append(nxt)
            j += 1

        profile["experience"].append({
            "company": company, "position": position,
            "start_date": start, "end_date": end,
            "description": "\n".join(desc_lines) if desc_lines else "",
            "achievements": []
        })
        i = j


def _parse_projects(lines: List[str], profile: Dict[str, Any]) -> None:
    """解析项目经历：'项目名 起止日期' 行 + 后续 bullet 描述"""
    i = 0
    while i < len(lines):
        cleaned = _strip_cid(lines[i]).strip()
        if not cleaned or cleaned.startswith("•") or cleaned.startswith("-"):
            i += 1
            continue
        # 项目行：含日期 或 含"—"破折号（项目名—描述）但不明显是公司
        has_date = bool(_DATE_RE.search(cleaned))
        has_dash = "—" in cleaned or "──" in cleaned or " - " in cleaned
        if not (has_date or has_dash):
            i += 1
            continue
        # 排除公司行
        if any(h in cleaned for h in COMPANY_HINTS) and not has_dash:
            i += 1
            continue

        start, end = _parse_dates(cleaned)
        # 项目名：去除日期、去除"至今/现在/Present"等残留、去除末尾分隔符
        body = _DATE_RE.sub("", cleaned)
        body = re.sub(r"(至今|现在|Present|present)\s*$", "", body)
        body = body.strip(" -–—,，·•")
        name = body

        # 收集后续 bullet 描述
        desc_lines = []
        j = i + 1
        while j < len(lines):
            nxt = _strip_cid(lines[j]).strip()
            if not nxt:
                j += 1
                continue
            if nxt.startswith("•") or nxt.startswith("-"):
                desc_lines.append(nxt)
                j += 1
            else:
                # 下一个项目行
                if _DATE_RE.search(nxt) or "—" in nxt:
                    break
                # 短行视为描述延续
                if len(nxt) < 50:
                    desc_lines.append(nxt)
                    j += 1
                else:
                    break

        profile["projects"].append({
            "name": name, "role": "", "description": "\n".join(desc_lines) if desc_lines else "",
            "start_date": start, "end_date": end, "tech_stack": []
        })
        i = j


def _parse_skills(lines: List[str], profile: Dict[str, Any]) -> None:
    """解析专业技能：'• 类别: 描述' bullets + 关键词兜底；类别按技能名归类"""
    seen = set()
    # 已有技能不再重复
    for s in profile["skills"]:
        seen.add(s["name"])

    # bullet 行：提取类别 + 关键技能
    for line in lines:
        cleaned = _strip_cid(line).strip()
        if not cleaned:
            continue
        # 去除 bullet 符号
        bullet = cleaned.lstrip("•-— ").strip()
        # 从描述中匹配技能库
        for sk in SKILL_LIB:
            if sk.lower() in bullet.lower() and sk not in seen:
                seen.add(sk)
                # 推断熟练度
                level = "熟悉"
                for lv_kw, lv_val in SKILL_LEVEL_HINTS.items():
                    if lv_kw in bullet:
                        level = lv_val
                        break
                # 优先用技能名标准类别；兜底由 bullet 行内容推断
                category = SKILL_CATEGORY_MAP.get(sk, "")
                if not category:
                    if any(k in bullet for k in ["编程", "语言"]):
                        category = "编程语言"
                    elif any(k in bullet for k in ["框架", "Framework"]):
                        category = "框架"
                    elif any(k in bullet for k in ["工具", "Tool"]):
                        category = "工具"
                    elif any(k in bullet for k in ["深度学习", "机器学习", "RAG", "Agent", "LLM", "Transformer"]):
                        category = "AI/ML"
                profile["skills"].append({"name": sk, "level": level, "category": category})


def _parse_certificates(lines: List[str], profile: Dict[str, Any]) -> None:
    """解析证书（简陋）：行内含'证书''认证'关键词的 bullet"""
    for line in lines:
        cleaned = _strip_cid(line).strip().lstrip("•-— ").strip()
        if not cleaned:
            continue
        if any(k in cleaned for k in ["证书", "认证", "Certification", "CET", "六级", "四级"]):
            profile["certificates"].append({
                "name": cleaned, "issuer": "", "date": "", "score": ""
            })


def _parse_honors(lines: List[str], profile: Dict[str, Any]) -> None:
    """科研与荣誉 → 写入 summary.strengths（OfferClaw 无独立字段）"""
    items = []
    for line in lines:
        cleaned = _strip_cid(line).strip().lstrip("•-— ").strip()
        if cleaned:
            items.append(cleaned)
    if items and not profile["summary"].get("strengths"):
        profile["summary"]["strengths"] = "\n".join(items)


def _rule_parse(text: str) -> Dict[str, Any]:
    """规则降级解析：预处理 → 分区 → 逐段结构化"""
    profile = empty_profile()
    # 预处理：保留原始行但去除 CID 噪声
    raw_lines = [l.rstrip() for l in text.splitlines()]
    lines = [l for l in raw_lines if l.strip()]
    # 顶部基本信息从头 8 行解析（按行计；空行不算）
    head_lines = lines[:8]

    _parse_basic(head_lines, profile)

    # 分区
    sections = _split_sections(lines)
    _parse_education(sections.get("education", []), profile)
    _parse_experience(sections.get("experience", []), profile)
    _parse_projects(sections.get("projects", []), profile)
    _parse_skills(sections.get("skills", []), profile)
    _parse_certificates(sections.get("certificates", []), profile)
    _parse_honors(sections.get("honors", []), profile)

    return profile


async def _llm_parse(text: str) -> Dict[str, Any]:
    """LLM 结构化解析（用户已配置 Key 时）"""
    from app.core.llm import get_gen_provider, Message

    provider = get_gen_provider()
    # 截断避免超长
    snippet = text[:8000] if len(text) > 8000 else text
    prompt = RESUME_PARSE_PROMPT.format(resume_text=snippet)
    messages = [Message(role="user", content=prompt)]
    response = await provider.chat(messages=messages, temperature=0.1, max_tokens=4000)
    content = (response.content or "").strip()
    # 去除可能的 markdown 代码块
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content).strip()
    data = json.loads(content)
    # 合并到空结构保证字段完整
    base = empty_profile()
    for k in base:
        if k in data:
            base[k] = data[k]
    return base


async def parse_resume(pdf_bytes: bytes) -> Tuple[Dict[str, Any], str, str]:
    """解析 PDF 简历

    Returns:
        (profile, text, source)
        - profile: OfferClaw 画像结构
        - text: 提取的原文（供前端展示/调试）
        - source: "llm" | "rules"
    """
    # 文本提取（损坏/加密/无文本的 PDF 在此兜底，避免 500）
    try:
        text = extract_text(pdf_bytes)
    except Exception as e:
        logger.error(f"PDF 文本提取失败: {e}", exc_info=True)
        return empty_profile(), "", "error"
    if not text.strip():
        return empty_profile(), "", "empty"

    # 优先 LLM
    try:
        from app.core.config import settings
        if getattr(settings, "llm_configured", False):
            profile = await _llm_parse(text)
            return profile, text, "llm"
    except Exception as e:
        logger.warning(f"LLM 解析失败，降级规则解析: {e}")

    # 规则降级
    try:
        profile = _rule_parse(text)
        return profile, text, "rules"
    except Exception as e:
        logger.error(f"规则解析失败: {e}", exc_info=True)
        return empty_profile(), text, "error"
