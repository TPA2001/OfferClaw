"""
求职内容生成服务

封装 LLM 调用，提供：
- JD 抓取与结构化提取
- 岗位匹配评分
- 简历生成（Markdown）
- 求职信生成
- 面试准备包生成
- 投递策略建议

所有方法接收 LLMProvider 实例，复用现有 LLM 抽象层。
"""

import json
import logging
import re
from typing import Optional

from app.core.llm import LLMProvider, LLMResponse, Message

logger = logging.getLogger("offerclaw.resume_service")


class ResumeService:
    """求职内容生成服务"""

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    # ============ 底层 LLM 调用 ============

    async def _chat(self, system: str, user: str, temperature: float = 0.7) -> str:
        """单轮对话，返回 assistant 文本"""
        messages = [
            Message(role="system", content=system),
            Message(role="user", content=user),
        ]
        resp: LLMResponse = await self.llm.chat(messages, temperature=temperature)
        return resp.content or ""

    async def _chat_json(self, system: str, user: str, temperature: float = 0.3) -> dict:
        """单轮对话，要求返回 JSON，做容错解析"""
        raw = await self._chat(system, user, temperature=temperature)
        return _safe_parse_json(raw)

    # ============ JD 抓取 ============

    async def extract_jd_from_url(self, url: str) -> dict:
        """
        从招聘页面 URL 抓取 JD 内容。

        使用 Playwright 抓取页面文本，再用 LLM 提取结构化信息。
        返回 {title, company, requirements[], responsibilities[], skills[], raw_text}
        """
        logger.info(f"抓取 JD 页面: {url}")
        raw_text = await self._fetch_page_text(url)

        if not raw_text or len(raw_text) < 50:
            return {
                "url": url,
                "title": "",
                "company": "",
                "raw_text": "",
                "error": "页面内容过少，可能是 JS 渲染失败或需要登录",
            }

        system = (
            "你是招聘信息提取专家。从给定的网页文本中提取岗位 JD 的结构化信息。"
            "只输出 JSON，不要任何解释。JSON 格式：\n"
            '{"title":"岗位名称","company":"公司名","location":"工作地点",'
            '"requirements":["任职要求1","任职要求2"],'
            '"responsibilities":["岗位职责1","岗位职责2"],'
            '"skills":["技能1","技能2"],'
            '"salary":"薪资描述","raw_text":"原始文本前500字"}'
        )
        user = f"网页 URL：{url}\n\n网页文本：\n{raw_text[:4000]}"

        try:
            data = await self._chat_json(system, user)
            data["url"] = url
            data.setdefault("raw_text", raw_text[:500])
            return data
        except Exception as e:
            logger.warning(f"JD 结构化失败，返回原始文本: {e}")
            return {
                "url": url,
                "title": "",
                "company": "",
                "raw_text": raw_text[:1000],
                "error": f"结构化失败：{e}",
            }

    async def _fetch_page_text(self, url: str) -> str:
        """抓取招聘页面的可见文本（无浏览器依赖，httpx + HTML 提取）"""
        try:
            import httpx
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
            async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers) as client:
                resp = await client.get(url)
                resp.raise_for_status()
            html = resp.text
            # 去除 script/style 及其内容
            html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
            # 标签 → 换行/空格
            html = re.sub(r"<[^>]+>", "\n", html)
            # HTML 实体解码
            import html as html_mod
            text = html_mod.unescape(html)
            text = re.sub(r"\n{3,}", "\n\n", text)
            return text.strip()
        except Exception as e:
            logger.warning(f"页面抓取失败（httpx）: {e}")
            return ""

    # ============ 岗位真实性判断 ============

    async def verify_authenticity(self, jd: dict | str, company: str = "") -> dict:
        """
        判断岗位真实性与风险，识别虚假/中介/培训贷/皮包公司等风险信号。

        Args:
            jd: JD 结构化 dict 或 JD 文本字符串
            company: 公司名（可选，辅助判断）

        Returns:
            {
                risk_level: "safe|low|medium|high|danger",
                risk_score: 0-100,            # 越高越危险
                authenticity_score: 0-100,    # 越高越可信
                signals: [{type, detail, severity}],
                summary: "一句话结论",
                advice: "具体建议"
            }
        """
        jd_text = jd if isinstance(jd, str) else json.dumps(jd, ensure_ascii=False)

        system = (
            "你是反招聘欺诈专家，深谙国内招聘平台的虚假岗位套路。"
            "请基于 JD 文本判断岗位真实性与风险等级。\n\n"
            "## 风险信号清单（逐条检查）\n"
            "1. **收费类**：要求培训费/押金/服装费/体检指定机构/入职前缴费\n"
            "2. **培训贷**：先培训后上岗/承诺高薪但需贷款培训/培训完安排工作\n"
            "3. **中介特征**：代招/合作企业/不写具体公司名/催加微信/HR名是英文名/多个公司共用一份JD\n"
            "4. **薪资异常**：区间过宽(差3倍以上)/远超市场水平/底薪+高提成话术/写面议但不说明\n"
            "5. **信息矛盾**：标题与描述不符/要求应届但薪资写资深水平/岗位职责与任职要求不匹配\n"
            "6. **要求模糊**：无明确技术栈/'学习能力强'代替技能/不限专业学历/门槛过低\n"
            "7. **皮包特征**：无具体办公地址/公司名查不到/注册资本极低/成立不到3个月大量招聘\n"
            "8. **话术异常**：急招/名额有限/当天入职/无需经验高薪/包吃包住高薪(低端岗位特征)\n"
            "9. **岗位错位**：标题是技术岗但内容是销售/标题是正式工但是劳务派遣\n\n"
            "## 风险等级定义\n"
            "- safe：无明显风险，信息完整可信\n"
            "- low：有轻微疑点但不影响投递\n"
            "- medium：存在多个可疑信号，建议谨慎核实\n"
            "- high：高度可疑，很可能是中介/培训贷/虚假岗位\n"
            "- danger：确认是骗局（收费/培训贷），绝对不要投\n\n"
            "只输出 JSON，不要任何解释：\n"
            '{"risk_level":"safe","risk_score":15,"authenticity_score":85,'
            '"signals":[{"type":"薪资异常","detail":"具体描述","severity":"low"}],'
            '"summary":"一句话结论","advice":"具体可执行的建议"}\n\n'
            "注意：risk_score 和 authenticity_score 互补（risk_score + authenticity_score = 100）。"
            "severity 取值：high/mid/low。signals 可为空数组（无风险时）。"
        )
        user = f"# 岗位 JD\n{jd_text}"
        if company:
            user = f"# 公司\n{company}\n\n" + user

        try:
            data = await self._chat_json(system, user, temperature=0.2)
            data.setdefault("risk_level", "unknown")
            data.setdefault("risk_score", 50)
            data.setdefault("authenticity_score", 50)
            data.setdefault("signals", [])
            data.setdefault("summary", "无法判断")
            data.setdefault("advice", "")
            # 修正分数互补关系
            if "risk_score" in data and "authenticity_score" not in data:
                data["authenticity_score"] = max(0, 100 - data["risk_score"])
            return data
        except Exception as e:
            logger.error(f"真实性判断失败: {e}")
            return {
                "risk_level": "unknown",
                "risk_score": 50,
                "authenticity_score": 50,
                "signals": [],
                "summary": "真实性判断服务暂时不可用",
                "advice": "建议人工核实公司工商信息和岗位真实性",
                "error": str(e),
            }

    # ============ 岗位匹配评分 ============

    async def score_job_match(self, profile: dict, jd: dict | str) -> dict:
        """
        评估用户画像与 JD 的匹配度。

        Args:
            profile: 用户画像 dict（basic_info/education/experience/skills/projects/summary/job_intent）
            jd: JD 结构化 dict 或 JD 文本字符串

        Returns:
            {score, level, dimensions{}, strengths[], gaps[], suggestion}
        """
        jd_text = jd if isinstance(jd, str) else json.dumps(jd, ensure_ascii=False)
        profile_text = _format_profile_for_llm(profile)

        system = (
            "你是资深技术招聘官，擅长评估候选人与岗位的匹配度。"
            "请基于用户画像和岗位 JD，从 5 个维度评分（0-100）：\n"
            "1. eligibility（硬性条件：学历/经验年限/地点/薪资是否匹配）\n"
            "2. skills（技能栈匹配度）\n"
            "3. experience（相关项目/工作经历匹配度）\n"
            "4. potential（成长潜力/学习能力信号）\n"
            "5. culture（基于画像的稳定性/求职意向匹配度）\n\n"
            "综合评分权重：eligibility 30% / skills 25% / experience 15% / potential 15% / culture 15%\n"
            "eligibility 维度若硬性不符（如学历不足、经验年限不够），给出 veto=true 表示一票否决。\n\n"
            "只输出 JSON：\n"
            '{"score":85,"level":"良好","veto":false,'
            '"dimensions":{"eligibility":{"score":80,"note":"..."},'
            '"skills":{"score":90,"note":"..."},"experience":{"score":75,"note":"..."},'
            '"potential":{"score":85,"note":"..."},"culture":{"score":80,"note":"..."}},'
            '"strengths":["优势1","优势2"],"gaps":["差距1","差距2"],'
            '"suggestion":"是否建议投递及原因"}\n\n'
            "level 取值：优秀(>=85) / 良好(70-84) / 一般(55-69) / 勉强(40-54) / 不匹配(<40)"
        )
        user = f"# 用户画像\n{profile_text}\n\n# 岗位 JD\n{jd_text}"

        try:
            data = await self._chat_json(system, user)
            data.setdefault("score", 0)
            data.setdefault("level", "未知")
            data.setdefault("veto", False)
            data.setdefault("strengths", [])
            data.setdefault("gaps", [])
            data.setdefault("suggestion", "")
            return data
        except Exception as e:
            logger.error(f"匹配评分失败: {e}")
            return {
                "score": 0,
                "level": "评分失败",
                "error": str(e),
                "suggestion": "评分服务暂时不可用，建议人工评估",
            }

    # ============ 简历生成 ============

    async def generate_resume(self, profile: dict, jd: dict | str | None = None) -> str:
        """
        根据画像 + JD 生成定制化 Markdown 简历。

        若提供 jd，会针对 JD 重点重排和强调匹配技能/经验。
        返回 Markdown 文本。
        """
        profile_text = _format_profile_for_llm(profile)
        jd_section = ""
        if jd:
            jd_text = jd if isinstance(jd, str) else json.dumps(jd, ensure_ascii=False)
            jd_section = f"\n\n# 目标岗位 JD（据此定制简历重点）\n{jd_text}"

        system = (
            "你是资深简历顾问，擅长撰写符合国内校招/社招审美的简历。要求：\n"
            "1. 输出 Markdown 格式，结构清晰：基本信息 / 教育经历 / 工作经历 / 项目经历 / 技能 / 自我评价\n"
            "2. 若提供了目标 JD：\n"
            "   - 在简历中突出与 JD 匹配的技能和经验，弱化无关内容\n"
            "   - 自我评价针对 JD 定制，体现匹配点而非通用模板\n"
            "   - 技能列表按 JD 优先级排序\n"
            "   - 项目经历优先展示与 JD 相关的，用 STAR 描述（情境-任务-行动-结果）\n"
            "3. 工作经历用动词开头，量化成果（如\"提升性能 40%\"而非\"负责性能优化\"）\n"
            "4. 校招简历控制在 1 页，社招最多 2 页内容量\n"
            "5. 不要编造经历，只能基于画像信息重组和润色；缺失信息用 [待补充] 占位\n"
            "6. 不输出任何解释，直接给出简历 Markdown"
        )
        user = f"# 用户画像\n{profile_text}{jd_section}"

        return await self._chat(system, user, temperature=0.5)

    # ============ 求职信生成 ============

    async def generate_cover_letter(self, profile: dict, jd: dict | str, company: str = "") -> str:
        """
        生成求职信/自荐信（Markdown）。
        """
        profile_text = _format_profile_for_llm(profile)
        jd_text = jd if isinstance(jd, str) else json.dumps(jd, ensure_ascii=False)

        system = (
            "你是求职信撰写专家，深谙国内校招/社招自荐信写法。要求：\n"
            "1. 输出 Markdown 格式求职信，300-500 字，分 3 段：\n"
            "   - 开头：表明意向岗位 + 从何处获知招聘 + 一句话亮点吸引\n"
            "   - 中段：用 2-3 个具体经历/项目证明与岗位的匹配（呼应 JD 要求）\n"
            "   - 结尾：表达加入意愿 + 期待面试机会 + 致谢\n"
            "2. 语气真诚专业，避免空话套话（如\"我非常热爱贵公司\"）\n"
            "3. 只基于画像信息，不编造经历\n"
            "4. 不输出解释，直接给求职信 Markdown"
        )
        user = f"# 用户画像\n{profile_text}\n\n# 目标公司\n{company or '（未指定）'}\n\n# 岗位 JD\n{jd_text}"

        return await self._chat(system, user, temperature=0.6)

    # ============ 面试准备包 ============

    async def prepare_interview(
        self, profile: dict, jd: dict | str, company: str = "", position: str = ""
    ) -> str:
        """
        生成面试准备包（Markdown）。
        含：公司调研方向 / 可能问题 / STAR 例子映射 / 反问问题 / 八股重点。
        """
        profile_text = _format_profile_for_llm(profile)
        jd_text = jd if isinstance(jd, str) else json.dumps(jd, ensure_ascii=False)

        system = (
            "你是资深面试辅导教练，熟悉国内互联网/科技公司面试流程。"
            "请基于用户画像和目标岗位，生成结构化面试准备包（Markdown）。包含：\n\n"
            "## 1. 面试流程预判\n"
            "- 预计几轮、每轮侧重（技术基础/项目深挖/系统设计/HR）\n\n"
            "## 2. 公司调研方向\n"
            "- 建议调研的公司业务、近期动态、技术栈、文化\n\n"
            "## 3. 可能的问题（按轮次）\n"
            "- 一面：技术基础/八股（列出 5-8 个高频问题）\n"
            "- 二面：项目深挖（针对画像中的项目，列出可能追问）\n"
            "- 三面：系统设计/架构（如适用）\n"
            "- HR 面：行为问题（离职原因/职业规划/薪资期望）\n\n"
            "## 4. STAR 例子映射\n"
            "- 从画像的项目/经历中，提炼 2-3 个可复用的 STAR 例子（情境-任务-行动-结果）\n"
            "- 标注每个例子适合回答哪类问题\n\n"
            "## 5. 技术八股重点\n"
            "- 基于 JD 技术栈，列出必须复习的知识点\n\n"
            "## 6. 反问问题\n"
            "- 给 3-5 个高质量反问（体现思考深度，避免百度可查的）\n\n"
            "## 7. 薄弱项提醒\n"
            "- 画像中相对 JD 的薄弱点，面试时如何回避或转化\n\n"
            "要求：只基于画像和 JD，不编造经历；不输出解释，直接给 Markdown。"
        )
        user = (
            f"# 用户画像\n{profile_text}\n\n"
            f"# 目标公司\n{company or '（未指定）'}\n\n"
            f"# 目标岗位\n{position or '（见 JD）'}\n\n"
            f"# 岗位 JD\n{jd_text}"
        )

        return await self._chat(system, user, temperature=0.5)

    # ============ 投递策略建议 ============

    async def get_application_advice(self, stats: dict) -> str:
        """
        基于投递统计数据，生成求职策略建议（Markdown）。
        """
        system = (
            "你是求职策略顾问。基于用户的投递统计数据，给出诊断和优化建议（Markdown）。包含：\n\n"
            "## 1. 现状诊断\n"
            "- 回复率/Offer 率是否健康，与市场基准对比\n"
            "- 漏斗哪一环节掉链子（简历挂/笔试挂/面试挂）\n\n"
            "## 2. 问题分析\n"
            "- 可能的原因（简历问题/投递方向/投递节奏/公司选择）\n\n"
            "## 3. 优化建议\n"
            "- 短期：接下来 1 周该怎么调整\n"
            "- 中期：投递策略/简历/面试的改进方向\n\n"
            "## 4. 投递节奏建议\n"
            "- 当前是否在求职窗口期，每日投递量建议\n\n"
            "要求：建议要具体可执行，不说空话；不输出解释，直接给 Markdown。"
        )
        user = f"# 用户投递统计\n```json\n{json.dumps(stats, ensure_ascii=False, indent=2)}\n```"

        return await self._chat(system, user, temperature=0.6)


# ============ 工具函数 ============

def _safe_parse_json(text: str) -> dict:
    """容错解析 LLM 输出的 JSON（可能带 ```json 代码块或前后多余文本）"""
    if not text:
        return {}
    # 去除代码块包裹
    text = text.strip()
    if text.startswith("```"):
        # 去掉首行 ```json 或 ```
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    # 尝试直接解析
    try:
        return json.loads(text)
    except Exception:
        pass
    # 尝试提取第一个 {...}
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    raise ValueError(f"无法解析 JSON: {text[:200]}")


def _format_profile_for_llm(profile: dict) -> str:
    """把用户画像 dict 格式化为 LLM 易读的文本"""
    parts = []

    basic = profile.get("basic_info") or {}
    if basic:
        parts.append(f"## 基本信息\n{json.dumps(basic, ensure_ascii=False, indent=2)}")

    edu = profile.get("education") or []
    if edu:
        parts.append(f"## 教育经历\n{json.dumps(edu, ensure_ascii=False, indent=2)}")

    exp = profile.get("experience") or []
    if exp:
        parts.append(f"## 工作经历\n{json.dumps(exp, ensure_ascii=False, indent=2)}")

    proj = profile.get("projects") or []
    if proj:
        parts.append(f"## 项目经历\n{json.dumps(proj, ensure_ascii=False, indent=2)}")

    skills = profile.get("skills") or []
    if skills:
        parts.append(f"## 技能\n{json.dumps(skills, ensure_ascii=False, indent=2)}")

    summary = profile.get("summary") or {}
    if summary:
        parts.append(f"## 自我评价\n{json.dumps(summary, ensure_ascii=False, indent=2)}")

    certs = profile.get("certifications") or []
    if certs:
        parts.append(f"## 证书荣誉\n{json.dumps(certs, ensure_ascii=False, indent=2)}")

    intent = profile.get("job_intent") or {}
    if intent:
        parts.append(f"## 求职意向\n{json.dumps(intent, ensure_ascii=False, indent=2)}")

    return "\n\n".join(parts) if parts else "（画像为空）"
