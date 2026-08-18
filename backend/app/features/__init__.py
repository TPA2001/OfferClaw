"""
OfferClaw Features 模块

借鉴 CareerDesk 的 features 架构，按业务域组织功能模块。
每个 feature 内部包含：
- service.py: 业务逻辑
- public.py: 对外公共接口（Agent Tool 和 API 都通过此边界访问）

OfferClaw 独有 features（CareerDesk 没有）：
- boss_search: Boss 直聘搜索 + 反爬降级链
- smart_fill: 智能表单填写
- job_verify: 岗位真实性判断

借鉴 CareerDesk 新增的 features：
- company_research: 公司调研
- mock_interview: 模拟面试
- journal: 求职日志/笔记
"""
