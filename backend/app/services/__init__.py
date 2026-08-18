"""Services 层 - 流程编排

组合 features/automation/core 完成复杂业务流程。各 service 通过具体模块导入：

- resume_service.ResumeService      简历/JD/评分/面试准备（6合一）
- boss_search.BossSearchService     Boss 搜索（三级降级链）
- smart_fill.SmartFillService       智能填写（字段提取编排）
- auto_filler.AutoFillerService     自动填表执行（CDP-based）
- playwright_runtime                Playwright 运行时管理
"""

# 注意：不在此处统一导出，保持 "按需从具体模块导入" 的约定，
# 避免 __init__ 触发不必要的模块加载（如 boss_search 依赖较重）。
