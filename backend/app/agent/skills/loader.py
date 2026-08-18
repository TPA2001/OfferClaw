"""
Skill 加载器

从 skills/ 目录读取 SKILL.md 文件，解析为 Skill 对象。
支持热加载和按用户意图匹配技能。

SKILL.md 格式示例：
---
name: emotional_support
description: 求职情绪支持，帮助用户应对求职焦虑
triggers:
  - 焦虑
  - 压力大
  - 想放弃
  - 没信心
tools:
  - get_followups
  - query_applications
---

# 技能指令

当用户表达求职焦虑/压力/挫败感时，你是求职心理教练...
（详细行为指令，注入到 system prompt）
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("offerclaw.agent.skills")

try:
    import yaml
except ImportError:
    yaml = None
    logger.warning("pyyaml 未安装，Agent Skills 机制将被禁用。请运行 pip install pyyaml")


@dataclass
class Skill:
    """技能定义"""
    name: str
    description: str
    triggers: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)  # 该技能推荐使用的工具
    instructions: str = ""  # 行为指令（注入 system prompt）
    source_file: str = ""   # 来源文件路径

    def matches(self, user_input: str) -> bool:
        """判断用户输入是否触发该技能"""
        text = user_input.lower()
        return any(t.lower() in text for t in self.triggers)

    def match_score(self, user_input: str) -> int:
        """返回触发关键词命中数（用于多技能排序）"""
        text = user_input.lower()
        return sum(1 for t in self.triggers if t.lower() in text)


class SkillLoader:
    """技能加载器"""

    def __init__(self, skills_dir: Optional[Path] = None):
        if skills_dir is None:
            # 默认从 agent/skills/skills/ 目录加载
            skills_dir = Path(__file__).parent / "skills"
        self.skills_dir = Path(skills_dir)
        self._skills: dict[str, Skill] = {}
        self._loaded = False

    def load(self) -> dict[str, Skill]:
        """加载所有 SKILL.md 文件"""
        if self._loaded:
            return self._skills

        if not self.skills_dir.exists():
            logger.warning(f"技能目录不存在: {self.skills_dir}")
            self._loaded = True
            return self._skills

        for md_file in sorted(self.skills_dir.glob("*.md")):
            try:
                skill = self._parse_skill_file(md_file)
                if skill:
                    self._skills[skill.name] = skill
                    logger.info(f"加载技能: {skill.name} (from {md_file.name})")
            except Exception as e:
                logger.error(f"解析技能文件失败 {md_file}: {e}")

        self._loaded = True
        return self._skills

    def _parse_skill_file(self, filepath: Path) -> Optional[Skill]:
        """解析单个 SKILL.md 文件"""
        if yaml is None:
            logger.warning(f"pyyaml 未安装，跳过技能文件 {filepath.name}")
            return None

        content = filepath.read_text(encoding="utf-8")

        # 解析 YAML front matter
        front_matter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
        if not front_matter_match:
            logger.warning(f"技能文件 {filepath.name} 缺少 YAML front matter")
            return None

        yaml_str = front_matter_match.group(1)
        instructions = front_matter_match.group(2).strip()

        try:
            meta = yaml.safe_load(yaml_str) or {}
        except yaml.YAMLError as e:
            logger.error(f"YAML 解析失败 {filepath.name}: {e}")
            return None

        name = meta.get("name", filepath.stem)
        description = meta.get("description", "")
        triggers = meta.get("triggers", []) or []
        tools = meta.get("tools", []) or []

        return Skill(
            name=name,
            description=description,
            triggers=triggers,
            tools=tools,
            instructions=instructions,
            source_file=str(filepath),
        )

    def get(self, name: str) -> Optional[Skill]:
        """按名称获取技能"""
        if not self._loaded:
            self.load()
        return self._skills.get(name)

    def list_skills(self) -> list[Skill]:
        """列出所有技能"""
        if not self._loaded:
            self.load()
        return list(self._skills.values())

    def match_skills(self, user_input: str, top_k: int = 3) -> list[Skill]:
        """根据用户输入匹配技能，返回最相关的 top_k 个"""
        if not self._loaded:
            self.load()

        scored = [(s, s.match_score(user_input)) for s in self._skills.values()]
        scored = [(s, score) for s, score in scored if score > 0]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in scored[:top_k]]

    def build_system_prompt_section(self, user_input: Optional[str] = None) -> str:
        """
        构建 system prompt 的技能段。

        如果提供 user_input，只注入匹配到的技能指令；
        否则注入所有技能的简要描述（作为能力声明）。
        """
        if not self._loaded:
            self.load()

        if user_input:
            matched = self.match_skills(user_input)
            if not matched:
                return ""

            sections = ["\n\n## 当前激活的技能"]
            for skill in matched:
                sections.append(f"\n### 技能：{skill.name}\n{skill.instructions}")
            return "\n".join(sections)

        # 无输入时，注入所有技能的能力声明
        if not self._skills:
            return ""

        sections = ["\n\n## 可用技能（按用户意图自动激活）"]
        for skill in self._skills.values():
            trigger_str = "、".join(skill.triggers[:5]) if skill.triggers else "无"
            sections.append(f"- **{skill.name}**：{skill.description}（触发词：{trigger_str}）")
        return "\n".join(sections)


# ===== 单例 =====
_loader: Optional[SkillLoader] = None


def get_skill_loader() -> SkillLoader:
    """获取技能加载器单例"""
    global _loader
    if _loader is None:
        _loader = SkillLoader()
    return _loader
