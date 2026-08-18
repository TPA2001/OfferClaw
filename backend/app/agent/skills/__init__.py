"""
Agent Skills 模块

借鉴 CareerDesk 的 skills 架构，通过 SKILL.md 文件定义可插拔的技能。
每个 skill 是一个 Markdown 文件，包含：
- name: 技能名
- description: 技能描述
- trigger: 触发条件（用户意图关键词）
- instructions: 行为指令（注入到 system prompt）
- tools: 该技能可用的工具列表（可选，用于工具过滤）

设计理念：
- 技能 = 领域知识 + 行为指令 + 工具集合
- SKILL.md 是声明式配置，无需写代码即可新增技能
- 技能可热加载，运行时按用户意图动态激活
- 与 OfferClaw 独有能力结合：Boss 搜索、智能填表、岗位真实性判断

OfferClaw 独有 skills（CareerDesk 没有）：
- boss_search: Boss 直聘搜索策略
- smart_fill: 智能表单填写
- job_verify: 岗位真实性判断

借鉴 CareerDesk 新增的 skills：
- emotional_support: 求职情绪支持
- interview_coach: 面试辅导
- career_strategy: 求职策略规划
"""

from .loader import SkillLoader, Skill, get_skill_loader

__all__ = ["SkillLoader", "Skill", "get_skill_loader"]
