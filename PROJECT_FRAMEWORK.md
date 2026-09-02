# OfferCabin 项目框架说明

本文档介绍 OfferCabin 的**标准化前后端项目框架**：目录布局、分层职责、入口与启动方式、约定规范。适合新成员快速理解项目骨架，也适合在维护时对照检查代码归属。

> 如需了解各模块的详细设计（数据流、工具列表、Skills 机制等），请参阅 [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)。

---

## 一、技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 后端 | Python 3.10+ / FastAPI / SQLAlchemy 2.0 | 异步 API + ORM |
| 数据库 | SQLite（默认）/ PostgreSQL（可切换） | 通过 `DATABASE_URL` 切换 |
| 前端 | 原生 HTML / CSS / JavaScript | 多页应用，`python -m http.server` 静态托管 |
| Agent | LLM Function Calling + 28 工具 + SKILL.md 技能 | 核心差异化能力 |
| LLM | OpenAI 兼容协议（GLM / DeepSeek / Qwen / GPT） | 模型分级：Agent 编排 + 内容生成 |
| 自动化 | Playwright（Chromium） | Boss 搜索 + 智能填表 |
| 依赖 | PEP 621 `pyproject.toml`（uv / pip 兼容） | 现代 Python 依赖管理 |
| 质量 | Ruff（lint + format） + pytest | 单一工具链 |

---

## 二、顶层目录布局

```
OfferCabin/
├── backend/          # 后端项目（Python FastAPI）
├── frontend/         # 前端项目（原生 HTML/CSS/JS）
│   └── web/
├── offercabin-extension/  # Chrome MV3 浏览器扩展（智能填表 + 本地画像）
├── docs/             # 项目文档
├── README.md         # 项目总览 + 快速开始
├── PROJECT_FRAMEWORK.md  # 本文档：框架说明
└── .gitignore
```

**约定**：
- `backend/` 与 `frontend/` 是两个**独立**项目，各自有自己的依赖与构建流程
- 后端通过 FastAPI 暴露 REST API，前端通过 HTTP 调用，**解耦部署**
- 文档统一放在 `docs/`，根目录只保留 `README.md` 与 `PROJECT_FRAMEWORK.md`

---

## 三、后端框架（backend/）

### 3.1 目录结构

```
backend/
├── app/                       # 应用主包
│   ├── main.py                # FastAPI 应用入口（app 实例 + 中间件 + 路由注册）
│   │
│   ├── api/                   # API 路由层（HTTP 边界）
│   │   ├── applications.py    #   投递管理 API
│   │   ├── automation.py      #   智能填写 & Boss 搜索 API
│   │   ├── profile.py         #   用户画像 API
│   │   └── agent.py           #   Agent 对话 API（SSE 流式）
│   │
│   ├── core/                  # Platform 层（基础设施）
│   │   ├── config.py          #   Pydantic Settings 集中配置
│   │   ├── database.py        #   SQLAlchemy 引擎/会话工厂
│   │   ├── auth.py            #   鉴权（demo / jwt / header 三模式）
│   │   ├── response.py        #   统一响应封装 {code, message, data}
│   │   ├── log_utils.py       #   结构化日志工具
│   │   ├── subscription.py    #   订阅/付费（预留）
│   │   └── llm/               #   LLM 抽象层（package，非单文件）
│   │       ├── base.py        #     LLMProvider 接口 + 数据结构
│   │       ├── openai_provider.py  OpenAI 兼容协议实现
│   │       ├── mock_provider.py    Mock 降级（无 API Key 时）
│   │       ├── retry_provider.py   指数退避重试装饰器
│   │       ├── factory.py     #     Provider 工厂（模型分级）
│   │       ├── events.py      #     流式事件类型
│   │       ├── errors.py      #     LLM 错误分类
│   │       └── serialization.py    消息序列化
│   │
│   ├── models/                # 数据库模型（SQLAlchemy ORM）
│   │   ├── application.py     #   Application + AgentSession
│   │   └── profile.py         #   Profile（用户画像）
│   │
│   ├── schemas/               # Pydantic 请求/响应模型（API 边界校验）
│   │   ├── applications.py
│   │   ├── profile.py
│   │   └── agent.py
│   │
│   ├── features/              # Features 层（业务能力，按域组织）
│   │   ├── company_research.py    公司调研
│   │   ├── mock_interview.py      模拟面试
│   │   └── journal.py             求职日志
│   │
│   ├── services/              # Orchestration 层（流程编排）
│   │   ├── resume_service.py      简历/JD/评分/面试准备（6合一）
│   │   ├── boss_search.py         Boss 搜索（三级降级）
│   │   ├── boss_html_search.py    HTML 降级搜索
│   │   ├── boss_utils.py          Boss 搜索工具函数
│   │   ├── smart_fill.py          智能填写编排
│   │   ├── auto_filler.py         自动填表执行（CDP-based）
│   │   └── playwright_runtime.py  Playwright 运行时管理
│   │
│   ├── automation/            # 表单自动化底层模块
│   │   ├── form_extractor.py     表单字段提取
│   │   └── field_matcher.py      字段语义匹配（LLM + 规则降级）
│   │
│   └── agent/                 # Agentic 层（Agent 系统）
│       ├── runtime/           #   运行时（loop / registry / state / events / base_tool）
│       ├── tools/             #   28 个工具（8 组）
│       ├── skills/            #   SKILL.md 声明式技能（6 个）
│       │   └── skills/        #     SKILL.md 文件目录
│       └── apps/              #   Agent 应用（job_agent 主 Agent）
│
├── tests/                     # 测试
│   ├── conftest.py            #   pytest 配置
│   ├── test_*.py              #   单元测试（自动收集）
│   └── integration/           #   集成测试脚本（需启动服务，不被 pytest 自动收集）
│       ├── e2e_legacy.py      #     Boss 搜索 + 表单提取 + 脚本生成
│       └── e2e_playwright.py  #     Playwright 自动填表 + 登录态
│
├── pyproject.toml             # PEP 621 依赖管理 + Ruff 配置
├── requirements.txt           # pip 兼容依赖（与 pyproject.toml 同步）
├── .env.example               # 环境变量示例
└── run.py                     # 启动入口（含 Windows 事件循环修正）
```

### 3.2 四层架构

后端采用**自底向上**的四层架构，每层只能调用下层，不可反向依赖：

```
┌──────────────────────────────────────────────────────────┐
│  API 层（api/）                                            │
│  HTTP 边界：路由、参数校验、鉴权、响应封装                 │
│  只做"翻译"，不含业务逻辑                                  │
├──────────────────────────────────────────────────────────┤
│  Orchestration 层（services/ + automation/）              │
│  流程编排：组合 features / core 完成复杂业务流程           │
│  如：Boss 搜索降级链、智能填表、简历生成                   │
├──────────────────────────────────────────────────────────┤
│  Features 层（features/ + agent/）                        │
│  业务能力：公司调研、模拟面试、Agent 工具/技能             │
│  每个 feature 通过 public 函数暴露接口                     │
├──────────────────────────────────────────────────────────┤
│  Platform 层（core/ + models/ + schemas/）                │
│  基础设施：配置、数据库、鉴权、LLM、响应封装、日志         │
└──────────────────────────────────────────────────────────┘
```

**分层规则**：
- `api/` 只调用 `services/` / `features/` / `core/`，不直接操作 ORM
- `services/` 编排 `features/` / `automation/` / `core/`
- `features/` / `agent/` 只通过 `core/` 访问基础设施
- `models/` 是纯数据模型，`schemas/` 是纯 API 契约，两者分离

### 3.3 入口与启动

**唯一启动入口**：[`backend/run.py`](file:///c:/Users/tpa/Desktop/code/AI/agent/OfferCabin/backend/run.py)

```bash
cd backend
python run.py            # 默认启动（生产/调试通用）
python run.py --reload   # 热重载（仅纯 API 开发，Playwright 可能异常）
```

**为什么不用 `uvicorn app.main:app` 直接启动？**
Windows 下 uvicorn 会强制使用 `SelectorEventLoop`，而 Playwright 依赖 `ProactorEventLoop` 创建子进程。`run.py` 在导入 uvicorn 前设置正确的事件循环策略，并 monkeypatch uvicorn 的 loop 安装器，确保 Windows 下 Playwright 正常工作。

**数据库自动初始化**：表会在首次启动时由 `app/main.py` 自动创建（`Base.metadata.create_all`），并对旧库做增量列追加迁移（`_migrate_applications_table` / `_migrate_profiles_table`）。**无需手动运行初始化脚本**。

### 3.4 配置管理

所有配置通过环境变量 / `.env` 文件加载，集中管理在 [`app/core/config.py`](file:///c:/Users/tpa/Desktop/code/AI/agent/OfferCabin/backend/app/core/config.py)：

```python
from app.core.config import settings
settings.database_url     # 数据库连接
settings.auth_mode        # demo / jwt / header
settings.agent_model      # Agent 编排模型
settings.gen_model        # 内容生成模型
```

**模型分级**（OfferCabin 特色）：
- **Agent 编排模型**（强模型）：GLM-4.5 / DeepSeek-V3 / GPT-4o，用于 function calling
- **内容生成模型**（快模型）：GLM-4-Flash / Qwen-Plus，用于简历/评分/面试准备
- 未配置 `GEN_*` 时自动复用 Agent provider（单模型场景）

### 3.5 统一响应封装

所有 API 遵循统一信封（见 [`app/core/response.py`](file:///c:/Users/tpa/Desktop/code/AI/agent/OfferCabin/backend/app/core/response.py)）：

```json
// 成功
{"code": 0, "message": "ok", "data": {...}}

// 失败
{"code": 40400, "message": "投递记录不存在", "detail": null}
```

业务码 = HTTP 状态码 × 100（如 `40400` 对应 HTTP 404），便于前端一眼对照。全局异常处理器确保所有错误（包括未捕获异常）都走统一信封，不向前端暴露内部堆栈。

### 3.6 测试约定

| 类型 | 位置 | 命名 | 运行 |
|------|------|------|------|
| 单元测试 | `tests/test_*.py` | `test_*.py` | `pytest`（自动收集） |
| 集成测试 | `tests/integration/e2e_*.py` | `e2e_*.py`（无 `test_` 前缀） | `python tests/integration/e2e_*.py`（手动） |

集成测试需要先启动后端服务，因此**不命名 `test_*` 前缀**，避免被 pytest 误收集。运行方式见各文件头部注释。

---

## 四、前端框架（frontend/web/）

### 4.1 目录结构

```
frontend/web/
├── index.html          # 首页（含投递看板）
├── agent.html          # Agent 对话页（SSE 流式）
├── smart-fill.html     # 智能填写页
├── profile.html        # 个人画像页
├── settings.html       # 设置页
├── dashboard.html      # 重定向到 index.html（兼容旧链接）
├── automation.html     # 重定向到 smart-fill.html（兼容旧链接）
├── test-form.html      # 智能填写测试表单（演示用）
├── config.js           # 前端配置（API 地址等）
├── motion.js           # 动画系统
└── styles/
    └── main.css        # 主样式
```

### 4.2 启动方式

```bash
cd frontend/web
python -m http.server 3000
```

访问 http://localhost:3000

### 4.3 前后端通信约定

- **API 基址**：由 [`config.js`](file:///c:/Users/tpa/Desktop/code/AI/agent/OfferCabin/frontend/web/config.js) 统一配置，默认 `http://localhost:8000/api/v1`
- **CORS**：后端通过 `CORS_ORIGINS` 环境变量配置允许的来源
- **鉴权**：根据 `AUTH_MODE`，前端在请求头携带 `Authorization: Bearer <token>`
- **响应格式**：所有接口返回统一信封 `{code, message, data}`，前端统一检查 `code === 0`
- **流式响应**：Agent 对话通过 SSE（Server-Sent Events）推送事件流

### 4.4 隐私保护边界

- **非敏感数据**（姓名、邮箱、教育经历等）：可存储云端，用于 Agent 编排
- **敏感数据**（身份证号、家庭住址等）：**仅存储在浏览器本地**，后端永不接触
- 智能填表时，敏感字段由前端本地读取并注入到 Playwright 页面，不经过后端

---

## 五、打包与部署

当前采用 **PyInstaller 单文件打包**（`backend/build_release.bat` + `offercabin.spec`），Docker 配置已移除。

```bash
cd backend
build_release.bat        # 生成单文件可执行程序（dist/）
```

- 打包产物自带前端静态资源（`_MEIPASS/frontend/web`）与本地数据目录（`exe 同目录/data`）
- **授权门控默认关闭**（免费分发，无需激活码）：`OFFERCABIN_LICENSE_GATE` 未设置时全部功能直接可用；如需启用授权校验，设置 `OFFERCABIN_LICENSE_GATE=1`（此时走 JWT 密钥激活，见 `app/core/license.py`）

---

## 六、代码规范与约定

### 6.1 Python 代码风格

- **工具**：Ruff（lint + format），配置在 `pyproject.toml`
- **行宽**：120 字符
- **引用风格**：双引号
- **导入排序**：isort 规则，`app` 为 first-party
- **类型注解**：鼓励但不强制（公共 API 接口必须标注）

### 6.2 命名约定

| 对象 | 约定 | 示例 |
|------|------|------|
| Python 模块/文件 | snake_case | `boss_search.py` |
| 类 | PascalCase | `BossSearchService` |
| 函数/变量 | snake_case | `get_boss_search_service` |
| 常量 | UPPER_SNAKE | `DEFAULT_CITY_CODE` |
| SKILL.md 技能名 | snake_case | `emotional_support` |
| 前端 HTML | kebab-case | `smart-fill.html` |
| 前端 JS 函数 | camelCase | `fetchDashboardStats` |

### 6.3 服务单例模式

每个 service 通过 `get_xxx_service()` 工厂函数暴露单例：

```python
# services/boss_search.py
_service: Optional[BossSearchService] = None

def get_boss_search_service() -> BossSearchService:
    global _service
    if _service is None:
        _service = BossSearchService(...)
    return _service
```

调用方按需从具体模块导入（不在 `services/__init__.py` 统一导出，避免触发不必要的模块加载）：

```python
from app.services.boss_search import get_boss_search_service
```

### 6.4 Agent 工具与技能

- **工具**：每个工具继承 `BaseTool`，实现 `arun()` 方法，注册到 `ToolRegistry`
- **技能**：每个技能是一个 `SKILL.md` 文件，声明触发关键词、推荐工具、行为指令
- **新增工具**：在 `agent/tools/` 下新建文件，注册到 `agent/tools/__init__.py`
- **新增技能**：在 `agent/skills/skills/` 下新建 `SKILL.md`，无需改代码

---

## 七、文档体系

| 文档 | 位置 | 内容 |
|------|------|------|
| 项目总览 | [`README.md`](file:///c:/Users/tpa/Desktop/code/AI/agent/OfferCabin/README.md) | 项目简介、功能列表、快速开始、工具/Skills 表 |
| **框架说明** | [`PROJECT_FRAMEWORK.md`](file:///c:/Users/tpa/Desktop/code/AI/agent/OfferCabin/PROJECT_FRAMEWORK.md) | 本文档：标准化框架结构 |
| 项目结构详解 | [`docs/PROJECT_STRUCTURE.md`](file:///c:/Users/tpa/Desktop/code/AI/agent/OfferCabin/docs/PROJECT_STRUCTURE.md) | 四层架构、模块详解、数据流 |
| Agent 架构设计 | [`docs/AGENT_ARCHITECTURE.md`](file:///c:/Users/tpa/Desktop/code/AI/agent/OfferCabin/docs/AGENT_ARCHITECTURE.md) | Agent 运行时、工具、技能设计 |
| Agent 使用指南 | [`docs/AGENT_MVP_GUIDE.md`](file:///c:/Users/tpa/Desktop/code/AI/agent/OfferCabin/docs/AGENT_MVP_GUIDE.md) | 启动、配置 LLM、API 参考 |
| 智能填写指南 | [`docs/SMART_FILL_GUIDE.md`](file:///c:/Users/tpa/Desktop/code/AI/agent/OfferCabin/docs/SMART_FILL_GUIDE.md) | 智能填写设计与使用 |

---

## 八、本次框架优化记录

本次将项目从"原型阶段"整理为"标准前后端项目"，主要变更：

### 删除的死代码
- `backend/app/core/llm.py`：被 `core/llm/` package 完全遮蔽，其中的 `chat_json` 函数不可达
- `backend/app/automation/form_filler.py`：已被 `services/auto_filler.py`（CDP-based）取代
- `backend/app/automation/browser.py`：10 行 re-export 桩，全项目零引用
- `backend/init_db.py`：与 `app/main.py` 启动时自动建表逻辑重复
- `快速启动指南.md`：描述的是不存在的 pnpm/浏览器扩展/PostgreSQL 架构，严重误导

### 修复的 Bug
- `backend/app/automation/field_matcher.py`：原 `from app.core.llm import chat_json` 导入不存在的函数（被 `core/llm/` package 遮蔽），导致 LLM 语义匹配路径静默失效。已改为通过 `get_gen_provider().chat()` 正确调用 LLM provider。

### 结构规范化
- 移除 `app/main.py` 中的重复 `if __name__ == "__main__"` 块，统一以 `run.py` 为唯一入口
- 将 `backend/_test_e2e.py` / `_test_playwright_e2e.py` 迁移到 `backend/tests/integration/`，命名 `e2e_*.py`（无 `test_` 前缀，避免 pytest 误收集）
- 更新 `automation/__init__.py`：移除已删除的 `FormFiller` 导出
- 更新 `services/__init__.py`：改为文档型 `__init__.py`，保持"按需从具体模块导入"的约定
- 同步更新 `README.md`、`docs/PROJECT_STRUCTURE.md`、`docs/AGENT_MVP_GUIDE.md` 中的过时内容
