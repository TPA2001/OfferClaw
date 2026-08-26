# OfferClaw — 求职 AI Agent 助手

> **一句话**：面向校招/社招求职者的 Agent 驱动求职管理平台 —— 覆盖「岗位发现 → 真实性判断 → 匹配评分 → 简历/面试准备 → 投递追踪 → 复盘」求职全流程。

![status](https://img.shields.io/badge/status-WIP-yellow) ![license](https://img.shields.io/badge/license-MIT-blue)

未配置 LLM API Key 时，所有 AI 功能自动降级为 Mock，可零成本体验完整流程。

---

## ✨ 核心能力

- **🤖 Agent 助手**：LLM + 28 个工具 + 6 个声明式技能，对话式完成画像管理、投递记录、看板统计、岗位分析、简历/求职信/面试准备
- **📊 投递看板**：六列状态看板 + 拖拽流转 + 统计概览 + 跟进提醒 + 漏斗/渠道/趋势分析 + 导入导出
- **🔍 岗位搜索**：BOSS 直聘三级降级链（登录态搜索 → 公开页解析 → 模拟数据）
- **📝 简历画像**：结构化画像 + PDF 简历导入自动解析 + 求职意向/技能/项目经历管理
- **🤖 智能填表**：网申表单字段提取 + LLM 语义匹配（配合 Chrome 扩展本地完成填写）
- **🎤 面试复盘**：面试记录 + LLM 分析表现 + 改进建议
- **🔒 隐私分层**：敏感信息（身份证/住址/银行卡等）仅存浏览器本地，后端永不落库

---

## 🚀 快速开始（3 步跑起来）

### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt

# 可选：Boss 搜索 / 智能填表需要浏览器自动化
playwright install chromium
```

> 需要 Python 3.10+。建议使用虚拟环境（`python -m venv .venv`）。

### 2. 配置 LLM（可选）

```bash
cp .env.example .env
```

编辑 `.env`，填入一个 OpenAI 兼容的 API Key（任选其一即可）：

```ini
# 智谱 GLM
AGENT_API_KEY=sk-xxx
AGENT_BASE_URL=https://open.bigmodel.cn/api/paas/v4
AGENT_MODEL=glm-4.5

# 或 DeepSeek
# AGENT_API_KEY=sk-xxx
# AGENT_BASE_URL=https://api.deepseek.com/v1
# AGENT_MODEL=deepseek-chat

# 或 通义千问（OpenAI 兼容模式）
# AGENT_API_KEY=sk-xxx
# AGENT_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
# AGENT_MODEL=qwen-plus
```

> 不配置也能启动，所有 LLM 功能自动降级为 Mock Provider。

### 3. 启动

```bash
python run.py
```

启动后访问 **http://localhost:8000** 即可使用全部功能（前端已由后端自动托管，数据库表首次启动自动创建）。

---

## ⚙️ 常用命令

| 命令 | 说明 |
|------|------|
| `python run.py` | 启动服务（**Windows 必须用此方式**，见 FAQ） |
| `python run.py --reload` | 热重载（仅纯 API 开发，Playwright 可能异常） |
| `pytest` | 运行单元测试 |
| `python tests/integration/e2e_*.py` | 运行集成测试（需先启动服务） |
| `build_release.bat` | PyInstaller 打包单文件发布版（dist/） |

---

## 📖 常用 API 地址

| 地址 | 说明 |
|------|------|
| `http://localhost:8000/` | 应用首页（投递看板） |
| `http://localhost:8000/docs` | Swagger API 文档 |
| `http://localhost:8000/health` | 健康检查 |

---

## 🧩 项目结构（精简）

```
OfferClaw/
├── backend/                 # Python FastAPI 后端
│   ├── app/
│   │   ├── api/             #   路由层（agent/applications/profile/automation/settings...）
│   │   ├── core/            #   基础设施（配置/数据库/鉴权/LLM 抽象/授权/限流）
│   │   ├── models/          #   ORM（Application/Profile/AgentSession）
│   │   ├── services/        #   业务编排（简历/Boss 搜索/智能填表）
│   │   ├── features/        #   业务能力（公司调研/模拟面试/日志）
│   │   ├── agent/           #   Agent 系统（28 工具 + 6 技能）
│   │   └── automation/      #   表单自动化底层
│   ├── run.py               #   唯一启动入口
│   └── requirements.txt
├── frontend/web/            # 前端单页应用（原生 HTML/CSS/JS，由后端托管）
├── offerclaw-extension/     # Chrome MV3 扩展（智能填表 + 本地画像）
└── docs/                    # 架构/Agent/使用文档
```

后端采用**四层架构**：API → Orchestration → Features → Platform，每层只能调用下层。

---

## ❓ 常见问题

**Q1：Windows 上启动报 `NotImplementedError`？**
必须用 `python run.py` 启动（脚本会设置 ProactorEventLoop），不要直接用 `uvicorn app.main:app`。

**Q2：没有 LLM API Key 能用吗？**
能。所有 LLM 功能自动降级为 Mock Provider，流程可完整跑通。

**Q3：Boss 搜索搜不到真实数据？**
需要登录态。未登录时自动降级到公开页解析 / 模拟数据；也可在设置页配置登录态。

**Q4：端口被占用？**
默认 8000。修改 `run.py` 中的 `port=8000`，或先停掉占用进程。

**Q5：数据库在哪？**
默认 `backend/data/offerclaw.db`（SQLite），切换 PostgreSQL 只需设置 `DATABASE_URL` 环境变量。

---

## 📚 文档

| 文档 | 内容 |
|------|------|
| [PROJECT_FRAMEWORK.md](PROJECT_FRAMEWORK.md) | 项目框架说明 |
| [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) | 四层架构与模块详解 |
| [docs/AGENT_ARCHITECTURE.md](docs/AGENT_ARCHITECTURE.md) | Agent 运行时/工具/技能设计 |
| [docs/AGENT_MVP_GUIDE.md](docs/AGENT_MVP_GUIDE.md) | Agent 使用指南与 API 参考 |
| [docs/SMART_FILL_GUIDE.md](docs/SMART_FILL_GUIDE.md) | 智能填写设计 |

---

## 🛠 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.10+ / FastAPI / SQLAlchemy 2.0 / SQLite（可切 PostgreSQL） |
| 前端 | 原生 HTML / CSS / JavaScript（6 套主题） |
| Agent | LLM Function Calling + 28 工具 + SKILL.md 声明式技能 |
| LLM | OpenAI 兼容协议（GLM / DeepSeek / Qwen / GPT） |
| 自动化 | Playwright（Chromium） |

---

## 📄 License

MIT License — 欢迎学习、使用、贡献。
