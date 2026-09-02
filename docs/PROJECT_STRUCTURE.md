# 项目结构

OfferCabin 采用 **四层架构**，借鉴 CareerDesk 的 features/orchestration/agentic/platform 分层，同时保持 OfferCabin 独有的 Boss 搜索、智能填表、岗位真实性判断等特色能力。

## 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│  Features 层（业务能力）                                      │
│  按业务域组织，每个 feature 含 service + public 边界           │
│  ├── company_research  公司调研                              │
│  ├── mock_interview    模拟面试                              │
│  └── journal           求职日志                              │
├─────────────────────────────────────────────────────────────┤
│  Orchestration 层（流程编排）                                 │
│  组合多个 feature/service 完成复杂流程                        │
│  ├── resume_service    简历/JD/评分/面试准备（6合一）          │
│  ├── boss_search       Boss 搜索（三级降级链）                │
│  ├── smart_fill        智能填写                              │
│  └── auto_filler       自动填表执行                          │
├─────────────────────────────────────────────────────────────┤
│  Agentic 层（Agent 系统）                                    │
│  LLM 驱动的智能体，通过工具调用完成求职全流程                  │
│  ├── runtime           循环引擎/工具注册/状态管理             │
│  ├── tools             28个工具（8组）                        │
│  ├── skills            SKILL.md 声明式技能（6个）             │
│  └── apps              job_agent 主 Agent                    │
├─────────────────────────────────────────────────────────────┤
│  Platform 层（基础设施）                                     │
│  ├── core              配置/数据库/鉴权/LLM/响应/日志         │
│  ├── models            数据库模型                            │
│  └── schemas           Pydantic 请求/响应模型                 │
└─────────────────────────────────────────────────────────────┘
```

## 目录结构

```
offercabin/
├── backend/                              # Python FastAPI 后端
│   ├── app/
│   │   │
│   │   ├── api/                          # === API 路由层 ===
│   │   │   ├── applications.py           # 投递管理 API（CRUD/批量/统计/跟进）
│   │   │   ├── automation.py             # 智能填写 & Boss 搜索 API
│   │   │   ├── profile.py                # 用户画像 API
│   │   │   └── agent.py                  # Agent 对话 API（SSE 流式）
│   │   │
│   │   ├── core/                         # === 基础设施层 ===
│   │   │   ├── config.py                 # Pydantic Settings 集中配置
│   │   │   ├── database.py               # SQLAlchemy 引擎/会话
│   │   │   ├── auth.py                   # 鉴权（demo/jwt/header 三模式）
│   │   │   ├── response.py               # 统一响应封装 {success/data/error}
│   │   │   ├── log_utils.py              # 日志工具
│   │   │   ├── subscription.py           # 订阅/付费相关（预留）
│   │   │   └── llm/                      # LLM 抽象层
│   │   │       ├── base.py               # LLMProvider 接口 + 数据结构
│   │   │       ├── openai_provider.py    # OpenAI 兼容协议实现
│   │   │       ├── mock_provider.py      # Mock 降级（无 API Key 时）
│   │   │       ├── retry_provider.py     # 指数退避重试装饰器
│   │   │       └── factory.py            # Provider 工厂（模型分级）
│   │   │
│   │   ├── models/                       # === 数据库模型 ===
│   │   │   ├── application.py            # Application + AgentSession
│   │   │   └── profile.py                # Profile（用户画像）
│   │   │
│   │   ├── schemas/                      # === Pydantic 请求/响应模型 ===
│   │   │   ├── applications.py           # ApplicationCreate/Update/Response
│   │   │   ├── profile.py                # ProfileUpdate/Response
│   │   │   └── agent.py                  # AgentRequest/Response/Event
│   │   │
│   │   ├── features/                     # === Features 层（业务能力）===
│   │   │   ├── __init__.py               # 模块说明
│   │   │   ├── company_research.py       # 公司调研（行业/概况/优势/风险）
│   │   │   ├── mock_interview.py         # 模拟面试（题集/答案评估）
│   │   │   └── journal.py                # 求职日志（含 JournalEntry 模型）
│   │   │
│   │   ├── services/                     # === Orchestration 层（流程编排）===
│   │   │   ├── resume_service.py         # 简历/JD/评分/真实性/面试准备（6合一）
│   │   │   ├── boss_search.py            # Boss 搜索主服务（三级降级）
│   │   │   ├── boss_html_search.py       # HTML 降级搜索
│   │   │   ├── boss_utils.py             # Boss 搜索工具函数
│   │   │   ├── smart_fill.py             # 智能填写服务
│   │   │   ├── auto_filler.py            # Playwright 自动填表
│   │   │   └── playwright_runtime.py     # Playwright 运行时管理
│   │   │
│   │   ├── automation/                   # === 表单自动化模块（底层）===
│   │   │   ├── form_extractor.py         # 表单字段提取（Playwright）
│   │   │   └── field_matcher.py          # 字段语义匹配（LLM + 规则降级）
│   │   │
│   │   ├── agent/                        # === Agentic 层（Agent 系统）===
│   │   │   ├── __init__.py               # 模块导出
│   │   │   │
│   │   │   ├── runtime/                  # Agent 运行时
│   │   │   │   ├── loop.py               # 循环引擎（流式 + 工具调用 + 确认机制）
│   │   │   │   ├── base_tool.py          # BaseTool 基类 + ToolResult
│   │   │   │   ├── registry.py           # ToolRegistry 工具注册中心
│   │   │   │   ├── state.py              # AgentState 会话状态/消息历史
│   │   │   │   └── events.py             # 事件流定义（ContentDelta/ToolCall等）
│   │   │   │
│   │   │   ├── tools/                    # Agent 工具（28个，8组）
│   │   │   │   ├── __init__.py           # 工具导出
│   │   │   │   ├── profile_tools.py      # 画像管理（2: get/update_profile）
│   │   │   │   ├── application_tools.py  # 投递管理（4: create/update/query/delete）
│   │   │   │   ├── dashboard_tools.py    # 看板统计（1: get_dashboard_stats）
│   │   │   │   ├── followup_tools.py     # 跟进搜索（4: followups/search/timeline/company）
│   │   │   │   ├── smart_fill_tools.py   # 智能填写（2: extract/match）
│   │   │   │   ├── job_tools.py          # 投递前准备（6: JD/评分/简历/求职信/面试/策略）
│   │   │   │   ├── job_eval_tools.py     # 岗位分析（3: 真实性/搜索/综合评估）
│   │   │   │   ├── feature_tools.py      # Feature工具（6: 调研/题集/评估/复盘/日志/周报）
│   │   │   │   ├── memory_tools.py       # 长期记忆（update_user_preference）
│   │   │   │   └── navigate_tools.py     # 视图导航（navigate_view）
│   │   │   │
│   │   │   ├── memory/                   # 长期记忆与画像演化（Phase 1）
│   │   │   │   ├── __init__.py           # 模块导出
│   │   │   │   ├── schema.py             # UserMemory 模型
│   │   │   │   ├── embedding.py          # 嵌入（有 Key 向量 / 无 Key hash 降级）
│   │   │   │   ├── store.py              # 存储 + 向量/关键词检索
│   │   │   │   ├── retrieval.py          # 双层记忆检索
│   │   │   │   └── evolution.py          # 画像异步演化（LLM 提炼）
│   │   │   │
│   │   │   ├── skills/                   # Agent Skills（声明式技能，独有）
│   │   │   │   ├── __init__.py           # 模块导出
│   │   │   │   ├── loader.py             # SkillLoader 加载器（YAML解析+意图匹配）
│   │   │   │   └── skills/               # SKILL.md 文件目录
│   │   │   │       ├── emotional_support.md  # 情绪支持
│   │   │   │       ├── interview_coach.md    # 面试辅导
│   │   │   │       ├── career_strategy.md    # 求职策略
│   │   │   │       ├── job_verify.md         # 岗位真实性判断（独有）
│   │   │   │       ├── boss_search.md        # Boss 搜索（独有）
│   │   │   │       └── smart_fill.md         # 智能填表（独有）
│   │   │   │
│   │   │   └── apps/                     # Agent 应用
│   │   │       ├── __init__.py
│   │   │       └── job_agent.py          # 求职主 Agent（28工具 + 6技能）
│   │   │
│   │   ├── mcp/                          # MCP 对外暴露层（零依赖手写，2024-11-05 协议）
│   │   │   ├── __init__.py               # 模块导出
│   │   │   ├── adapters.py               # OfferCabinMcp：工具适配 + JSON-RPC 路由（可单测）
│   │   │   └── stdio.py                  # MCP stdio 传输主循环
│   │   │
│   │   ├── core/tracing.py               # 可观测性：Tracer + 本地导出（TRACE_ENABLED 开关）
│   │   │
│   │   └── main.py                       # FastAPI 应用入口
│   │
│   ├── evals/                            # 自动化评测（Phase 2）
│   │   └── datasets/                     # Golden Dataset（岗位推荐/面试复盘/画像查询）
│   │
│   ├── scripts/                          # 独立运行脚本
│   │   ├── mcp_server.py                 # MCP Server 入口（--transport stdio|sse）
│   │   └── eval_agent.py                 # 自动化评测脚本（Markdown 报告 + 彩色摘要）
│   │
│   ├── tests/                            # 测试
│   │   ├── conftest.py                   # pytest 配置
│   │   ├── test_agent_state.py           # Agent 状态测试
│   │   ├── test_applications.py          # 投递管理测试
│   │   ├── test_auth.py                  # 鉴权测试
│   │   ├── test_field_matcher.py         # 字段匹配测试
│   │   ├── test_log_utils.py             # 日志工具测试
│   │   ├── test_memory.py                # 长期记忆与画像演化测试（Phase 1）
│   │   ├── test_eval_regression.py       # 评测回归测试（Phase 2）
│   │   ├── test_mcp.py                   # MCP Server 适配层测试（Phase 3）
│   │   ├── test_response_envelope.py     # 响应封装测试
│   │   └── integration/                  # 集成测试（需启动服务，不被 pytest 自动收集）
│   │       ├── e2e_legacy.py             # 端到端测试：Boss 搜索 + 表单提取 + 脚本生成
│   │       └── e2e_playwright.py         # Playwright 端到端测试：自动填表 + 登录态
│   │
│   ├── pyproject.toml                    # PEP 621 依赖管理 + Ruff 配置
│   ├── requirements.txt                  # pip 兼容依赖
│   ├── .env.example                      # 环境变量示例
│   └── run.py                            # 启动入口（含 Windows 事件循环修正）
│
├── frontend/web/                         # 前端单页应用
│   ├── index.html                        # 首页
│   ├── dashboard.html                    # 投递看板
│   ├── agent.html                        # Agent 对话
│   ├── automation.html                   # 智能填写
│   ├── profile.html                      # 个人画像
│   ├── settings.html                     # 设置
│   ├── smart-fill.html                   # 智能填写（独立页）
│   ├── test-form.html                    # 表单测试页
│   ├── motion.js                         # 动画系统
│   ├── config.js                         # 前端配置
│   └── styles/
│       └── main.css                      # 主样式
│
├── docker/                               # Docker 配置
│   ├── Dockerfile.backend                # 后端 Dockerfile
│   └── docker-compose.yml                # Docker Compose
│
├── docs/                                 # 文档
│   ├── PROJECT_STRUCTURE.md              # 本文档
│   ├── AGENT_ARCHITECTURE.md             # Agent 架构设计
│   ├── AGENT_MVP_GUIDE.md                # Agent MVP 指南
│   └── SMART_FILL_GUIDE.md               # 智能填写指南
│
├── README.md                             # 项目说明
└── .gitignore
```

## 核心模块详解

### 1. Features 层（业务能力）

借鉴 CareerDesk 的 features 架构，按业务域组织功能模块。每个 feature 包含：
- **Service 类**：业务逻辑实现
- **public 边界函数**：对外统一接口（`get_xxx_service()`）

| Feature | 文件 | 能力 | 数据模型 |
|---------|------|------|---------|
| company_research | [company_research.py](file:///c:/Users/tpa/Desktop/code/AI/agent/OfferCabin/backend/app/features/company_research.py) | 公司调研报告（行业/概况/优势/风险/面试建议/薪资） | 无（纯 LLM） |
| mock_interview | [mock_interview.py](file:///c:/Users/tpa/Desktop/code/AI/agent/OfferCabin/backend/app/features/mock_interview.py) | 面试题集生成 + 答案评估 | 无（纯 LLM） |
| journal | [journal.py](file:///c:/Users/tpa/Desktop/code/AI/agent/OfferCabin/backend/app/features/journal.py) | 求职日志 + 面试复盘 + 周报 | JournalEntry |

### 2. Orchestration 层（流程编排）

组合多个 feature/service 完成复杂流程：

| Service | 文件 | 职责 |
|---------|------|------|
| ResumeService | [resume_service.py](file:///c:/Users/tpa/Desktop/code/AI/agent/OfferCabin/backend/app/services/resume_service.py) | JD抓取/真实性判断/匹配评分/简历生成/求职信/面试准备/投递策略（6合一） |
| BossSearchService | [boss_search.py](file:///c:/Users/tpa/Desktop/code/AI/agent/OfferCabin/backend/app/services/boss_search.py) | Boss 直聘搜索（wapi→HTML→mock 三级降级） |
| SmartFillService | [smart_fill.py](file:///c:/Users/tpa/Desktop/code/AI/agent/OfferCabin/backend/app/services/smart_fill.py) | 智能表单填写（字段提取+语义匹配） |

### 3. Agentic 层（Agent 系统）

LLM 驱动的智能体系统，是 OfferCabin 的核心差异化能力。

#### 3.1 Agent 运行时（runtime/）

- **AgentLoop**：循环引擎，执行 LLM → tool_calls → 工具执行 → 结果反馈 → LLM 循环
- **ToolRegistry**：工具注册中心，管理 28 个工具
- **AgentState**：会话状态，管理消息历史和待确认操作
- **事件流**：ContentDelta / ToolCallStart / ToolResultEvent / ConfirmRequiredEvent / DoneEvent

#### 3.2 Agent 工具（tools/）

28 个工具，按业务域分 8 组：

| 工具组 | 文件 | 工具数 | 工具列表 |
|--------|------|--------|---------|
| 画像管理 | profile_tools.py | 2 | get_profile, update_profile |
| 投递管理 | application_tools.py | 4 | create/update/query/delete_application |
| 看板统计 | dashboard_tools.py | 1 | get_dashboard_stats |
| 跟进搜索 | followup_tools.py | 4 | get_followups, search_applications, get_timeline_stats, get_company_stats |
| 智能填写 | smart_fill_tools.py | 2 | extract_form_fields, match_fields_to_profile |
| 投递前准备 | job_tools.py | 6 | extract_job_description, score_job_match, generate_resume, generate_cover_letter, prepare_interview, get_application_advice |
| 岗位分析 | job_eval_tools.py | 3 | verify_job_authenticity, search_jobs, evaluate_job |
| Feature工具 | feature_tools.py | 6 | research_company, generate_interview_questions, evaluate_interview_answer, review_interview, create_journal_entry, generate_weekly_summary |

#### 3.3 Agent Skills（skills/）

OfferCabin 独有的声明式技能机制。每个 SKILL.md 包含：
- **name**：技能名
- **description**：技能描述
- **triggers**：触发关键词列表
- **tools**：推荐使用的工具
- **instructions**：行为指令（注入 system prompt）

| Skill | 触发场景 | 说明 | 独有 |
|-------|---------|------|------|
| emotional_support | 焦虑/压力/挫败感 | 求职情绪支持 | |
| interview_coach | 面试准备/模拟/复盘 | 面试辅导教练 | |
| career_strategy | 投递策略/回复率低 | 求职策略诊断 | |
| job_verify | 质疑岗位真实性 | 反招聘欺诈专家 | ✅ |
| boss_search | 搜岗位/找工作 | Boss 搜索顾问 | ✅ |
| smart_fill | 填表/网申 | 智能填表助手 | ✅ |

#### 3.4 Agent 应用（apps/）

- **job_agent.py**：求职主 Agent，集成 28 工具 + 6 技能
  - `create_job_agent()`：创建 Agent 实例
  - `build_system_prompt()`：构建 system prompt（含 skills 能力声明）
  - `build_tool_registry()`：构建全部业务工具注册表，供 Agent 循环与 MCP Server 复用（`app/mcp/adapters.py` 调用此函数暴露工具）
  - `JOB_AGENT_PROMPT`：基础系统提示词

### 5. MCP 对外暴露层（mcp/，Phase 3）

把 OfferCabin 的 Agent 业务工具以 **Model Context Protocol（2024-11-05）** 暴露给外部 AI 平台（Claude Desktop / Cursor / 其他 MCP 客户端）。

**为什么零依赖手写**：官方 mcp SDK 强依赖 `pydantic>=2.10` / 新版 starlette，与项目锁定的 fastapi 0.111（要求 starlette<0.38）冲突。本项目工具已用 JSON Schema 描述参数（`BaseTool.parameters`），按 MCP 规范回填 `inputSchema` 即可，无需引入冲突依赖。

| 文件 | 职责 |
|------|------|
| adapters.py | `OfferCabinMcp`：工具适配（list_tools/call_tool）+ JSON-RPC 路由（initialize/ping/tools/list/tools/call/错误码），可独立单测 |
| stdio.py | MCP stdio 传输主循环：每行一条 JSON-RPC，读 stdin / 写 stdout |
| scripts/mcp_server.py | 入口：`--transport stdio`（默认）或 `--transport sse`（FastAPI 子应用，HTTP+SSE），`--list-tools` 打印清单 |

**开放能力**：复用 `build_tool_registry` 一次性暴露全部 28 个业务工具；无状态、每次调用新建 DB 会话，支持并发。

**运行方式**：
```bash
python scripts/mcp_server.py --list-tools     # 查看将暴露的工具
python scripts/mcp_server.py                   # stdio（本地 MCP 客户端接入）
python scripts/mcp_server.py --transport sse --port 8100   # HTTP+SSE（远程）
```
环境变量 `MCP_USER_ID` 指定对外操作的用户（默认 `mcp-user`）。需要人工二次确认的敏感操作在 MCP 环境下无法二次确认，会以挂起 + `action_id` 返回。

### 4. Platform 层（基础设施）

| 模块 | 文件 | 职责 |
|------|------|------|
| 配置 | config.py | Pydantic Settings 集中管理（env + computed_field） |
| 数据库 | database.py | SQLAlchemy 引擎/会话工厂 |
| 鉴权 | auth.py | demo/jwt/header 三模式鉴权 |
| LLM | llm/ | LLM 抽象层（Provider 接口 + 工厂 + 重试） |
| 响应 | response.py | 统一响应封装 {success/data/error} |
| 日志 | log_utils.py | 结构化日志工具 |

## 数据流

### Agent 对话流程

```
用户输入
  ↓
API (api/agent.py)
  ↓
create_job_agent() → AgentLoop
  ↓
AgentState.add_user(input)
  ↓
┌─ AgentLoop._loop() ──────────────────────────┐
│                                              │
│  LLM.chat_stream(messages, tools)            │
│    ↓                                         │
│  ├── content delta → ContentDelta event      │
│  └── tool_calls → ToolCallStart event        │
│         ↓                                    │
│  ToolRegistry.get(name).arun(args)           │
│    ├── 普通工具 → ToolResult                  │
│    └── 需确认 → ConfirmRequired event        │
│         ↓                                    │
│  AgentState.add_tool_result()                │
│    ↓                                         │
│  继续下一轮 LLM 调用                          │
│                                              │
└──────────────────────────────────────────────┘
  ↓
DoneEvent → AgentState.persist()
  ↓
SSE 响应完成
```

### 岗位分析流程

```
用户给出 JD URL/文本
  ↓
evaluate_job 工具
  ├── _resolve_jd() → 抓取/解析 JD
  ├── verify_authenticity() → 真实性判断（并行）
  └── score_job_match() → 匹配度评分（并行）
  ↓
综合决策（risk_level + match_score → verdict）
  ↓
返回结构化报告
```

## 设计原则

1. **Feature 边界**：每个 feature 通过 public 函数暴露接口，Agent Tool 只通过 public 接口访问
2. **工具单一职责**：每个工具只做一件事，复杂流程由 Agent 编排
3. **Skills 可插拔**：SKILL.md 声明式配置，新增技能无需改代码
4. **模型分级**：Agent 编排用强模型，内容生成用快模型
5. **优雅降级**：无 API Key → Mock Provider；Boss 搜索 → 三级降级；Skills 加载失败 → 基础 prompt
6. **隐私保护**：敏感数据不经过后端，由前端本地处理
