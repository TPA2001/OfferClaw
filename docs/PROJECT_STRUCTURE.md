# 项目结构

OfferClaw 采用标准的 Python Web 项目结构。

## 目录说明

```
offerclaw/
├── backend/              # Python 后端服务
│   ├── app/
│   │   ├── api/         # API 路由
│   │   │   ├── applications.py  # 投递管理 API
│   │   │   ├── automation.py    # 智能填写 API
│   │   │   ├── profile.py       # 用户画像 API
│   │   │   └── resumes.py       # 简历管理 API
│   │   │
│   │   ├── core/        # 核心模块
│   │   │   ├── database.py      # 数据库连接
│   │   │   ├── auth.py          # 用户认证
│   │   │   ├── llm.py           # LLM 调用
│   │   │   └── config.py        # 配置管理
│   │   │
│   │   ├── models/      # 数据库模型
│   │   │   ├── application.py   # 投递记录模型
│   │   │   ├── profile.py       # 用户画像模型
│   │   │   └── resume.py        # 简历模型
│   │   │
│   │   ├── schemas/     # Pydantic Schema
│   │   │   ├── application.py
│   │   │   ├── profile.py
│   │   │   └── resume.py
│   │   │
│   │   ├── automation/  # 智能填写模块（核心）
│   │   │   ├── form_extractor.py   # 表单字段提取
│   │   │   ├── form_filler.py      # 表单填写执行
│   │   │   └── field_matcher.py    # 字段语义匹配
│   │   │
│   │   └── utils/       # 工具函数
│   │
│   ├── tests/           # 测试
│   ├── requirements.txt
│   └── .env             # 配置文件
│
├── frontend/            # Web 前端
│   ├── web/             # Web 应用
│   │   ├── index.html          # 首页
│   │   ├── dashboard.html      # 投递看板
│   │   ├── automation.html     # 智能填写
│   │   ├── profile.html        # 个人画像
│   │   └── styles/
│   │       └── main.css
│   │
│   └── extension/       # 浏览器扩展
│       └── (TypeScript + Vite)
│
├── docs/                # 文档
│   ├── PROJECT_STRUCTURE.md    # 项目结构
│   ├── API.md                  # API 文档
│   └── DEPLOYMENT.md           # 部署文档
│
├── scripts/             # 工具脚本
│   └── setup.sh                # 安装脚本
│
├── docker/              # Docker 配置
│   ├── Dockerfile.backend
│   └── docker-compose.yml
│
├── .gitignore
├── README.md
└── LICENSE
```

## 核心模块

### backend/app/automation/

智能填写模块是 OfferClaw 的核心竞争力：

- **form_extractor.py**: 自动识别页面表单字段
- **form_filler.py**: 根据匹配结果执行填写
- **field_matcher.py**: 使用 LLM 进行语义匹配

### backend/app/api/

RESTful API 接口：

- `/api/v1/applications` - 投递记录管理
- `/api/v1/automation` - 智能填写接口
- `/api/v1/profiles` - 用户画像管理
- `/api/v1/resumes` - 简历附件管理

### frontend/web/

单页面 Web 应用：

- 首页：项目介绍和快速入口
- 看板：投递记录可视化管理
- 智能填写：自动化填写功能
- 个人画像：用户信息维护