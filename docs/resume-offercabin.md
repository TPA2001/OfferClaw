# 项目经历 — OfferCabin（简历用）

> 两个版本：完整版适合「项目经历」占比较高的简历（如校招技术岗、项目一页纸）；精简版适合一页纸简历中的第二/第三项目。按需删改，数字均可被面试追问验证。

---

## 完整版

**OfferCabin — 求职投递管理平台**（个人全栈项目，独立开发）
GitHub：github.com/TPA2001/OfferCabin ｜ 技术栈：Python / FastAPI / SQLAlchemy / SQLite（可切换 PostgreSQL）/ JWT / 原生 JS SPA / Docker / LLM Agent / MCP / Pytest

- 独立设计并开发面向校招/社招求职者的投递管理 Web 平台：六列状态看板（拖拽流转 + 漏斗/渠道/趋势统计分析）、简历画像（PDF 导入自动解析）、面试复盘、社区广场（发帖/评论/点赞/举报）与岗位投递分享等模块，支持 Docker Compose 一键部署与邀请码注册的账号运营模式。
- 设计多租户账号体系：基于 JWT 实现注册/登录/改密/找回密码全流程，采用 PBKDF2-SHA256 密码哈希与 token_version 版本控制（改密后旧令牌即时失效），所有业务数据按 user_id 严格隔离，无邮件服务场景下设计了「服务端令牌 + 管理员转交」的找回密码方案。
- 构建工具化 LLM Agent 助手：通过函数调用完成画像管理、投递记录增删查、看板统计、岗位真实性判断等任务；实现用户偏好长期记忆的自动沉淀与画像演化、工具调用全链路 Tracing，并搭建黄金数据集自动化评测回归（evals）保障 Agent 质量。
- 基于 JSON-RPC 零依赖手写 MCP（Model Context Protocol）Server，支持 stdio 与 HTTP+SSE 双传输，将 27 个业务工具以标准协议开放给 Claude Desktop、Cursor 等外部 AI 平台；单向通道下敏感操作设计为「挂起 + action_id」待确认机制。
- 落地社区 UGC 安全与治理方案：投递链接白名单校验（仅 http/https，拒绝内网/IP 直连，防 SSRF）、用户级滑动窗口限流、LLM 内容预审（异常降级放行 + 违规自动隐藏）、LIKE 查询通配符转义、举报达阈值自动隐藏。
- 建立工程规范：统一响应信封 + 业务错误码到 HTTP 状态码的集中映射；编写 152 个 Pytest 用例，覆盖账号全流程、多用户数据隔离、看板 CRUD、Agent 状态机、MCP 适配与评测回归。

---

## 精简版（3 条，适合一页纸简历）

**OfferCabin — 求职投递管理平台**（个人全栈项目）
GitHub：github.com/TPA2001/OfferCabin ｜ FastAPI / SQLAlchemy / JWT / LLM Agent / MCP / Docker

- 独立开发多用户求职投递管理平台（看板 + 简历画像 + 面试复盘 + 社区），设计 JWT 多租户账号体系与数据隔离方案，Docker Compose 一键部署，152 个 Pytest 用例保障质量。
- 构建工具化 LLM Agent：实现长期记忆沉淀、工具调用 Tracing 与黄金数据集自动化评测；零依赖手写 MCP Server（stdio/SSE 双传输），将 27 个业务工具开放给 Claude Desktop 等外部 AI 平台。
- 落地 UGC 安全治理：链接白名单防 SSRF、用户级限流、LLM 内容预审 + 举报自动隐藏，兼顾开放社区与平台安全。

---

## 面试可能被追问的点（提前准备）

| 简历表述 | 可能的追问 | 答题抓手 |
|---|---|---|
| JWT 多租户 / token_version | 为什么改密要让旧 token 失效？怎么实现的？ | 用户表存 token_version，签发时写入 claims，校验时比对；改密/reset 时 +1 |
| 27 个 MCP 工具 | 为什么不用官方 SDK？MCP 协议核心是什么？ | 避免与现有依赖栈冲突；JSON-RPC 2.0、initialize 握手、tools/list、tools/call、stdio/SSE 传输 |
| 黄金数据集评测 | 评测集怎么构建？指标是什么？ | 典型任务 → 期望工具调用序列/结果校验，CI 跑回归，防止改 prompt 引入退化 |
| 防 SSRF | 具体拦了什么？ | 仅 http/https，拒绝 localhost/内网段/IP 直连/IPv6 绕过 |
| LLM 预审降级 | LLM 挂了怎么办？ | Mock/异常时放行但记日志，靠举报阈值兜底 |
| 152 个测试 | 双 fixture 区别？ | 单用户语义（覆盖鉴权）vs 真实 JWT 全链路 |
