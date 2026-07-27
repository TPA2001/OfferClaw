# OfferClaw - 校招求职管理平台

一个面向校招求职者的全流程管理工具，集成投递看板、智能填写、简历管理等核心功能。

## 项目简介

OfferClaw 是一个帮助校招求职者系统化管理投递全流程的浏览器扩展+Web应用。通过看板式界面追踪投递状态，配合智能填写助手大幅提升求职效率。

## 核心功能

### 📊 投递看板
- 投递记录管理（创建、编辑、删除）
- 状态流转追踪（已投递 → 笔试中 → 面试中 → 已录用/已拒绝）
- 时间线可视化
- 拖拽看板视图
- 统计面板（回复率、Offer率、平均等待天数）
- 标签分类、来源追踪、数据导出

### 🤖 智能填写助手（核心竞争力）
- 表单字段自动识别（input/select/textarea/checkbox/radio/contenteditable）
- LLM 语义匹配（用户画像 ↔ 表单字段）
- React/Vue 框架兼容（nativeInputValueSetter 触发 input 事件）
- 敏感数据本地存储（隐私保护）
- 置信度评估（低置信度字段提示人工确认）
- 两种模式：生成控制台脚本（用户粘贴执行）/ Playwright 后台自动填写

### 🔍 Boss 直聘岗位搜索
- 复用本地 Chrome 登录态（userDataDir 持久化 Cookie）
- httpx 直连 Boss wapi 接口（参考 boss-cli 反爬策略）
- 反爬降级：触发风控时自动降级为模拟数据并提示
- 搜索结果可一键创建投递记录

## 项目结构

```
offerclaw/
├── backend/              # Python FastAPI 后端
│   ├── app/
│   │   ├── api/         # API 路由（applications/automation/profile/agent）
│   │   ├── core/        # 核心模块（数据库、鉴权、LLM）
│   │   ├── models/      # 数据库模型（application/profile）
│   │   ├── automation/  # 智能填写模块（字段提取/匹配/填写）
│   │   ├── services/    # 服务层（boss_search/smart_fill/auto_filler/playwright_runtime）
│   │   └── agent/       # Agent 运行时与工具
│   ├── data/            # 运行时数据（浏览器 profile 等，已 gitignore）
│   ├── init_db.py       # 数据库初始化
│   └── requirements.txt
│
└── frontend/web/        # 单页面应用（dashboard/smart-fill/agent/profile 等）
```

## 技术栈

- **后端**：Python 3.12 + FastAPI + SQLAlchemy + SQLite（默认，可切 PostgreSQL）
- **前端**：原生 HTML/CSS/JavaScript
- **自动化**：Playwright + Python（headless/headful Chrome）
- **LLM**：OpenAI 兼容协议（GPT-4o / 通义千问 / DeepSeek 等）

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/your-username/offerclaw.git
cd offerclaw
```

### 2. 安装依赖

```bash
# 安装 Python 依赖
cd backend
pip install -r requirements.txt

# 安装 Playwright
playwright install chromium
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填入你的 API Key
```

### 4. 初始化数据库

```bash
python init_db.py
```

### 5. 启动服务

```bash
# 启动后端
python -m uvicorn app.main:app --reload --port 8000

# 启动前端（新终端）
cd ../frontend/web
python -m http.server 3000
```

### 6. 访问应用

- **首页**：http://localhost:3000
- **看板**：http://localhost:3000/dashboard.html
- **智能填写**：http://localhost:3000/automation.html
- **API 文档**：http://localhost:8000/docs

## API 接口

### 投递管理

- `POST /api/v1/applications` - 创建投递记录
- `GET /api/v1/applications` - 获取投递列表（可按状态/公司/优先级过滤）
- `GET /api/v1/applications/{id}` - 获取单条投递记录
- `PUT /api/v1/applications/{id}` - 更新投递记录（支持部分更新，显式传 null 可清空字段）
- `PATCH /api/v1/applications/{id}/status` - 快速更新状态（看板拖拽用）
- `DELETE /api/v1/applications/{id}` - 删除投递记录
- `POST /api/v1/applications/batch` - 批量导入
- `GET /api/v1/applications/stats/overview` - 看板统计概览（漏斗/渠道/优先级）
- `GET /api/v1/applications/stats/followups` - 跟进提醒（待笔试/待面试/待回复 offer/长期未回）

### 智能填写 & Boss 搜索

- `POST /api/v1/automation/extract-from-url` - 从 URL 提取表单字段
- `POST /api/v1/automation/match` - 字段语义匹配
- `POST /api/v1/automation/generate-script` - 生成浏览器控制台填写脚本
- `POST /api/v1/automation/auto-fill` - Playwright 后台自动填表
- `POST /api/v1/automation/boss-search` - Boss 直聘岗位搜索
- `GET /api/v1/automation/login-status` - 检查登录态
- `POST /api/v1/automation/open-login` - 打开登录页（headful，用户手动登录）

### 鉴权

通过环境变量 `AUTH_MODE` 配置：
- `demo`（默认）：任意 token 返回 demo-user-123，便于本地开发
- `jwt`：校验 HS256 JWT（SECRET_KEY 签名），从 sub claim 取 user_id
- `header`：从 X-User-ID 请求头读取 user_id

## 隐私保护

OfferClaw 严格遵守隐私保护原则：

- ✅ 姓名、手机号、邮箱等非敏感数据可存储在云端
- 🔒 身份证号、家庭住址等敏感数据**仅存储在浏览器本地**
- 🔒 后端永不接触原始敏感数据
- 🔒 填表时由扩展从本地读取并直接注入页面字段

## 开发指南

启动开发环境：

```bash
# 后端（在 backend 目录）
python -m uvicorn app.main:app --reload --port 8000

# 前端（在 frontend/web 目录）
python -m http.server 5173
```

数据库迁移：后端启动时会自动执行 SQLite 友好的列追加迁移（`app/main.py` 中的 `_migrate_*` 函数），旧库无需手动操作。

环境变量详见 `backend/.env.example`。

## 许可证

MIT License

## 联系方式

OfferClaw Team