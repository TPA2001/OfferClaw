# OfferClaw — 求职 AI Agent

> ⚠️ **项目状态：积极开发中（WIP）**。核心框架已就绪，部分功能（Boss 真实搜索、智能填表自动执行、Agent 工具调用）依赖外部登录态 / LLM 配置，未配置时会自动降级到 Mock 或 HTML 公开页数据。欢迎 Star / Issue / PR。

一个面向校招与社招求职者的 **Agent 驱动**求职管理平台。通过 LLM + 工具调用 + 声明式技能机制，覆盖从「岗位发现 → 真实性判断 → 匹配评分 → 简历/面试准备 → 投递追踪 → 复盘」的求职全流程。

---

## 一、项目能做什么

### 🤖 Agent 能力（核心）
OfferClaw Agent 集成 **28 个工具（8 组）**，并按用户意图激活 **6 个声明式技能**：

| 分组 | 工具 | 说明 |
|------|------|------|
| 画像管理 | `get_profile` / `update_profile` | 查看/更新用户画像 |
| 投递管理 | `create_application` / `update_application` / `query_applications` / `delete_application` | 投递记录 CRUD |
| 看板统计 | `get_dashboard_stats` | 看板数据概览 |
| 跟进搜索 | `get_followups` / `search_applications` / `get_timeline_stats` / `get_company_stats` | 跟进提醒与统计分析 |
| 智能填写 | `extract_form_fields` / `match_fields_to_profile` | 表单提取与字段匹配 |
| 投递前准备 | `extract_job_description` / `score_job_match` / `generate_resume` / `generate_cover_letter` / `prepare_interview` / `get_application_advice` | JD分析/评分/简历/求职信/面试准备/策略建议 |
| 岗位分析 | `verify_job_authenticity` / `search_jobs` / `evaluate_job` | 真实性判断/Boss搜索/综合评估 |
| Feature 工具 | `research_company` / `generate_interview_questions` / `evaluate_interview_answer` / `review_interview` / `create_journal_entry` / `generate_weekly_summary` | 公司调研/面试题/答案评估/面试复盘/日志/周报 |

**Agent Skills（声明式，SKILL.md 即技能）**：

| 技能 | 触发场景 | 说明 |
|------|---------|------|
| `emotional_support` | 焦虑/压力/挫败感 | 求职情绪支持，先共情后建议 |
| `interview_coach` | 面试准备/模拟/复盘 | 面试辅导教练模式 |
| `career_strategy` | 投递策略/回复率低 | 数据驱动的求职策略诊断 |
| `job_verify` | 质疑岗位真实性 | 反招聘欺诈专家模式 |
| `boss_search` | 搜岗位/找工作 | Boss 搜索顾问模式 |
| `smart_fill` | 填表/网申 | 智能填表助手模式 |

### 📊 投递看板
- 六列状态看板（已投递 → 笔试中 → 面试中 → 已录用 / 已拒绝 / 已撤回），拖拽切换状态
- 统计概览（投递数/回复率/Offer率/平均等待天数）+ 跟进提醒（今日待办/即将面试/offer到期/长期未回复）
- 漏斗 / 渠道 / 优先级 / 时间趋势统计
- 拒绝阶段细分（简历初筛挂 / 笔试挂 / 一面挂 / 二面挂 / HR面挂 / offer谈崩 / HC没有 / 主动放弃 …）
- 创建/编辑模态框、导入导出、搜索筛选

### 🔍 岗位搜索（Boss 直聘）
- **三级降级链**：真实登录态搜索 → 公开 HTML 页解析 → 模拟数据
- 登录态检测 + 反爬检测横幅
- 城市筛选 / 分页 / 岗位卡片
- 搜索结果一键加入投递看板

### 📝 简历画像
- 结构化用户画像（基本信息/教育/工作/技能/项目/证书/自我总结）
- Agent 可读写画像，用于简历生成 / 岗位匹配评分 / 智能填表

### 🤖 智能填表
- 网申表单字段自动提取（Playwright 渲染页面）
- LLM 语义匹配表单字段与画像
- **隐私分层**：敏感数据（身份证号/住址）仅存浏览器本地，后端永不接触

### 🎤 面试复盘
- 面试记录 / LLM 辅助分析表现 / 改进建议
- 与 Agent 面试辅导技能联动

### 🎨 设置
- **6 套主题**（纸质档案 / 午夜墨色 / 深林 / 海洋 / 复古 / 极简）
- 外观密度切换（紧凑/标准/宽松）
- LLM 配置（运行时持久化、Provider 优先级、连通性测试）
- 健康检查面板（数据库 / LLM Provider / 鉴权模式）

---

## 二、项目架构

OfferClaw 采用 **四层架构**（Platform → Features → Orchestration → API），每层只能调用下层：

```
┌─────────────────────────────────────────────────┐
│  API 层（api/）                                  │
│  HTTP 边界：路由、参数校验、鉴权、统一响应封装    │
├─────────────────────────────────────────────────┤
│  Orchestration 层（services/ + automation/）     │
│  流程编排：Boss 搜索降级链 / 智能填表 / 简历生成  │
├─────────────────────────────────────────────────┤
│  Features 层（features/ + agent/）               │
│  业务能力：公司调研 / 模拟面试 / Agent 工具与技能 │
├─────────────────────────────────────────────────┤
│  Platform 层（core/ + models/ + schemas/）       │
│  基础设施：配置 / 数据库 / 鉴权 / LLM / 响应封装  │
└─────────────────────────────────────────────────┘
```

### 目录结构

```
offerclaw/
├── backend/                          # Python FastAPI 后端
│   ├── app/
│   │   ├── api/                      # API 路由层
│   │   │   ├── agent.py              # Agent 对话（SSE 流式）
│   │   │   ├── applications.py       # 投递管理
│   │   │   ├── automation.py         # 智能填写 & Boss 搜索
│   │   │   ├── profile.py            # 用户画像
│   │   │   ├── journal.py            # 求职日志
│   │   │   ├── settings.py           # 设置 & LLM 配置
│   │   │   └── auth.py               # 鉴权
│   │   ├── core/                     # 基础设施层
│   │   │   ├── config.py / config_store.py  # 配置 + 运行时持久化
│   │   │   ├── database.py / auth.py / response.py / log_utils.py
│   │   │   ├── rate_limit.py / security.py / subscription.py
│   │   │   └── llm/                  # LLM 抽象层（base/openai/mock/retry/factory）
│   │   ├── models/                   # SQLAlchemy ORM（application/profile/user）
│   │   ├── schemas/                  # Pydantic 请求/响应模型
│   │   ├── features/                 # Feature 模块（company_research/mock_interview/journal）
│   │   ├── services/                 # 服务层（resume/boss_search/smart_fill/auto_filler/playwright）
│   │   ├── automation/               # 表单自动化底层（form_extractor/field_matcher）
│   │   └── agent/                    # Agent 系统
│   │       ├── runtime/              # 运行时（loop/registry/state/events/base_tool）
│   │       ├── tools/                # 28 工具（8 组）
│   │       ├── skills/               # SKILL.md 声明式技能加载器
│   │       └── apps/                 # job_agent 主 Agent
│   ├── tests/                        # 单元测试 + 集成测试
│   ├── pyproject.toml / requirements.txt / .env.example
│   └── run.py                        # 唯一启动入口（含 Windows 事件循环修正）
│
├── frontend/web/                     # 前端单页应用
│   ├── index.html                    # 主壳（顶栏 + 侧栏 + 视图挂载点）
│   ├── app/
│   │   ├── api.js / app.js / router.js / markdown.js
│   │   └── views/                    # chat / kanban / jobs / profile / smart-fill / interview / settings
│   ├── styles/main.css               # 主题系统
│   ├── motion.js                     # 动画系统
│   └── config.js
│
├── docker/                           # Dockerfile.backend / Dockerfile.frontend / docker-compose.yml / nginx.conf
├── docs/                             # PROJECT_STRUCTURE / AGENT_ARCHITECTURE / AGENT_MVP_GUIDE / SMART_FILL_GUIDE
├── PROJECT_FRAMEWORK.md              # 框架说明
└── README.md
```

---

## 三、技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.10+ / FastAPI / SQLAlchemy 2.0 / SQLite（可切 PostgreSQL） |
| 前端 | 原生 HTML / CSS / JavaScript + 自研动画与主题系统 |
| Agent | LLM Function Calling + 28 工具 + SKILL.md 声明式技能 |
| LLM | OpenAI 兼容协议（GLM-4.5 / DeepSeek / Qwen / GPT-4o） |
| 自动化 | Playwright（Chromium，headless / headful） |
| 依赖 | PEP 621 `pyproject.toml`（uv / pip 兼容） |
| 质量 | Ruff（lint + format） + pytest |

### 模型分级（OfferClaw 特色）
- **Agent 编排模型**（强模型）：GLM-4.5 / DeepSeek-V3 / GPT-4o，用于 function calling
- **内容生成模型**（快模型）：GLM-4-Flash / Qwen-Plus，用于简历/评分/面试准备
- 未配置 `GEN_*` 时自动复用 Agent provider（单模型场景）

---

## 四、完成度

| 模块 | 状态 | 说明 |
|------|------|------|
| 投递看板 | ✅ 已完成 | CRUD / 拖拽 / 统计 / 跟进 / 导入导出 |
| 简历画像 | ✅ 已完成 | 结构化画像 + Agent 读写 |
| 求职日志 / 周报 | ✅ 已完成 | 日志 CRUD + 周报生成 |
| 面试复盘 | ✅ 已完成 | 记录 + LLM 分析 |
| 设置（主题/LLM/健康） | ✅ 已完成 | 6 主题 + 运行时 LLM 配置 |
| Agent 运行时 | ✅ 已完成 | 循环引擎 / 工具注册 / 技能加载 |
| Agent 28 工具 | ✅ 已完成 | 8 组工具全部注册 |
| Boss 岗位搜索 | 🟡 部分完成 | 真实搜索需登录态；未登录时降级到 HTML 公开页 / 模拟数据 |
| 岗位真实性判断 | ✅ 已完成 | 9 类风险信号 + 5 级风险等级（LLM 驱动） |
| 智能填表（提取/匹配） | ✅ 已完成 | 字段提取 + LLM 语义匹配 |
| 智能填表（自动执行） | 🟡 部分完成 | 依赖目标站点登录态，需 headful 浏览器介入 |
| 简历/求职信/面试准备 | ✅ 已完成 | LLM 驱动，按 JD 定制 |
| Docker 部署 | 🟡 部分完成 | 后端镜像就绪，前端 nginx 镜像待完善 |
| 用户系统 | 🟡 部分完成 | demo / jwt / header 三模式鉴权，多用户隔离基础已就绪 |
| 测试覆盖 | 🟡 部分完成 | 单元测试覆盖核心模块，集成测试需手动运行 |

> 未配置 LLM API Key 时，所有 LLM 驱动功能会自动降级为 Mock Provider，可用于本地体验流程。

---

## 五、快速开始

### 1. 克隆项目

```bash
git clone https://github.com/TPA2001/OfferClaw.git
cd OfferClaw
```

### 2. 安装依赖

```bash
cd backend
pip install -r requirements.txt
playwright install chromium
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 LLM API Key（未配置时自动降级为 Mock Provider）
```

### 4. 启动服务

```bash
# 后端（数据库表会在首次启动时自动创建）
python run.py

# 前端（新终端）
cd ../frontend/web
python -m http.server 5173
```

> Windows 用户必须使用 `python run.py` 而非 `uvicorn app.main:app`，
> 因为 `run.py` 会设置 ProactorEventLoop，Playwright 在 Windows 下依赖它创建子进程。

### 5. 访问应用

- 首页 / AI 对话：http://localhost:5173/
- 投递看板：http://localhost:5173/kanban
- 岗位搜索：http://localhost:5173/jobs
- 简历画像：http://localhost:5173/profile
- 智能填表：http://localhost:5173/smart-fill
- 面试复盘：http://localhost:5173/interview
- 设置：http://localhost:5173/settings
- API 文档：http://localhost:8000/docs

---

## 六、隐私保护

OfferClaw 严格遵守隐私保护原则：

- ✅ 姓名、手机号、邮箱等**非敏感数据**可存储在云端，用于 Agent 编排
- 🔒 身份证号、家庭住址等**敏感数据仅存储在浏览器本地**
- 🔒 后端永不接触原始敏感数据
- 🔒 Agent 不询问敏感信息，填表时由前端本地读取并注入

---

## 七、文档

| 文档 | 内容 |
|------|------|
| [PROJECT_FRAMEWORK.md](PROJECT_FRAMEWORK.md) | 标准化前后端项目框架说明 |
| [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) | 四层架构、模块详解、数据流 |
| [docs/AGENT_ARCHITECTURE.md](docs/AGENT_ARCHITECTURE.md) | Agent 运行时、工具、技能设计 |
| [docs/AGENT_MVP_GUIDE.md](docs/AGENT_MVP_GUIDE.md) | 启动、配置 LLM、API 参考 |
| [docs/SMART_FILL_GUIDE.md](docs/SMART_FILL_GUIDE.md) | 智能填写设计与使用 |

---

## 八、路线图

- [ ] Boss 搜索登录态自动化（扫码登录持久化）
- [ ] 智能填表自动执行（headful 流程编排）
- [ ] 多用户体系完善（注册/登录/数据隔离）
- [ ] Docker 一键部署（前端 nginx 镜像）
- [ ] 移动端适配
- [ ] 更多 Agent 技能（薪资谈判 / offer 比较）

---

## 九、许可证

MIT License — 欢迎学习、使用、贡献。
