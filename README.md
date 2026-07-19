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
- 表单字段自动识别（input/select/textarea）
- LLM 语义匹配（用户画像 ↔ 表单字段）
- React/Vue 框架兼容
- 敏感数据本地存储（隐私保护）
- 置信度评估（低置信度字段提示人工确认）

### 📄 简历附件管理
- 多版本简历上传
- 版本命名、默认设置
- 文件上传/下载/删除

## 项目结构

```
offerclaw/
├── backend/              # Python FastAPI 后端
│   ├── app/
│   │   ├── api/         # API 路由
│   │   ├── core/        # 核心模块（数据库、认证、LLM）
│   │   ├── models/      # 数据库模型
│   │   ├── schemas/     # Pydantic Schema
│   │   ├── automation/  # 智能填写模块（核心）
│   │   └── utils/       # 工具函数
│   └── tests/
│
├── frontend/            # Web 前端
│   ├── web/             # 单页面应用
│   └── extension/       # 浏览器扩展
│
├── docs/                # 文档
└── docker/              # Docker 配置
```

## 技术栈

- **后端**：Python 3.12 + FastAPI + SQLite/PostgreSQL + Redis
- **前端**：原生 HTML/CSS/JavaScript + Chrome Extension MV3
- **自动化**：Playwright + Python
- **LLM**：OpenAI GPT-4o / Anthropic Claude / 阿里通义千问

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
- `GET /api/v1/applications` - 获取投递列表
- `PATCH /api/v1/applications/{id}` - 更新投递记录
- `DELETE /api/v1/applications/{id}` - 删除投递记录
- `GET /api/v1/applications/export/csv` - 导出 CSV

### 智能填写

- `POST /api/v1/automation/extract` - 提取表单字段
- `POST /api/v1/automation/match` - 字段语义匹配
- `POST /api/v1/automation/fill` - 执行表单填写

### 简历管理

- `POST /api/v1/resumes` - 上传简历
- `GET /api/v1/resumes` - 获取简历列表
- `GET /api/v1/resumes/{id}/download` - 下载简历
- `DELETE /api/v1/resumes/{id}` - 删除简历

## 隐私保护

OfferClaw 严格遵守隐私保护原则：

- ✅ 姓名、手机号、邮箱等非敏感数据可存储在云端
- 🔒 身份证号、家庭住址等敏感数据**仅存储在浏览器本地**
- 🔒 后端永不接触原始敏感数据
- 🔒 填表时由扩展从本地读取并直接注入页面字段

## 开发指南

详细的开发文档请查看 [docs/](./docs/):

- [项目结构](./docs/PROJECT_STRUCTURE.md)
- [API 文档](./docs/API.md)
- [部署文档](./docs/DEPLOYMENT.md)

## 许可证

MIT License

## 联系方式

OfferClaw Team