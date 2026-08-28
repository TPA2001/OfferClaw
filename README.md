# OfferClaw — 求职投递看板（多用户账号版）

> **一句话**：面向校招/社招求职者的投递管理平台 —— 投递看板 + 简历画像 + 面试复盘 + Agent 助手，支持网页服务化部署与多账号售卖。

![status](https://img.shields.io/badge/status-beta-green) ![license](https://img.shields.io/badge/license-MIT-blue)

未配置 LLM API Key 时，所有 AI 功能自动降级为 Mock，可零成本体验完整流程。

---

## ✨ 核心能力

- **📊 投递看板**：六列状态看板 + 拖拽流转 + 统计概览 + 跟进提醒 + 漏斗/渠道/趋势分析 + 导入导出
- **👤 账号体系**：注册/登录/修改密码/找回密码，多用户数据完全隔离（JWT 鉴权）
- **📝 简历画像**：结构化画像 + PDF 简历导入自动解析 + 求职意向/技能/项目经历管理
- **🎤 面试复盘**：面试记录 + LLM 分析表现 + 改进建议
- **🤖 Agent 助手**：LLM + 工具化对话，完成画像管理、投递记录、看板统计、岗位真实性判断、简历/求职信/面试准备
- **👥 社区广场**：用户交流板块（简历优化/面试经验/Offer 抉择/求助），发帖 + 楼中楼评论 + 点赞收藏 + 举报 + AI 内容预审
- **📣 投递分享**：共享公司官网招聘入口（不局限于单个岗位），按行业标签（互联网/游戏/央国企/外企等）分类，一键跳转官网投递 + 一键加入投递看板 + 即将截止筛选

> 已下线：BOSS 直聘搜索、智能填表（依赖用户本地浏览器登录态与 Playwright，不适合网页服务形态）。

---

## 🚀 快速开始（Docker 部署，推荐）

```bash
# 1. 构建并启动（首次构建约 1-2 分钟）
docker compose up -d --build

# 2. 访问
#    http://localhost:8000   → 注册账号 → 登录 → 开始使用

# 3. 生产部署必改项（docker-compose.yml）
#    - SECRET_KEY：改成强随机密钥（openssl rand -hex 32）
#    - REGISTRATION_INVITE_CODE：设置后注册必须携带邀请码（账号售卖场景）
```

数据默认存在 `./data/offerclaw.db`（SQLite 卷挂载），升级容器不丢数据。

### 账号管理（售卖/运营）

```bash
# 创建账号（可配合邀请码模式售卖）
docker exec -it offerclaw python /app/scripts/admin.py create <用户名> <邮箱> <密码>
# 重置密码（同时注销该用户全部登录）
docker exec -it offerclaw python /app/scripts/admin.py reset <用户名或邮箱> <新密码>
# 停用账号 / 列出账号
docker exec -it offerclaw python /app/scripts/admin.py disable <用户名或邮箱>
docker exec -it offerclaw python /app/scripts/admin.py list
```

### 找回密码说明

无邮件服务时采用「管理员从日志取令牌」模式：用户在找回密码页提交邮箱 → 服务端生成一次性令牌（1 小时有效）并写入服务端日志 → 管理员把令牌转交用户完成重置。

```bash
docker logs offerclaw | grep 找回密码
```

---

## 🛠 本地开发

```bash
cd backend
pip install -r requirements.txt
python run.py            # 启动 http://localhost:8000（前端由后端托管）
```

环境变量（`.env` 或系统环境）：

| 变量 | 默认 | 说明 |
|------|------|------|
| `AUTH_MODE` | `jwt` | `jwt`=多用户账号模式；`open`=单用户本地模式（仅本地开发） |
| `SECRET_KEY` | 开发默认值 | JWT 签名密钥，**生产必须修改** |
| `DATABASE_URL` | `backend/data/offerclaw.db` | 可切换 PostgreSQL |
| `REGISTRATION_INVITE_CODE` | 空 | 设置后注册必须携带邀请码 |
| `AUTH_RESET_TOKEN_IN_RESPONSE` | `0` | `1` 时找回密码令牌直接随响应返回（仅内网调试） |
| `AUTH_TOKEN_TTL_HOURS` | `168` | 登录有效期（小时） |
| `AGENT_API_KEY` 等 | 空 | LLM 配置，不配则 AI 功能为 Mock |

---

## 🧩 项目结构（精简）

```
OfferClaw/
├── backend/                 # Python FastAPI 后端
│   ├── app/
│   │   ├── api/             #   auth（账号）/ applications（看板）/ profile / journal / agent / settings
│   │   ├── core/            #   配置 / 数据库 / JWT 鉴权 / LLM / 统一响应
│   │   ├── models/          #   ORM（User / Application / Profile / AgentSession）
│   │   ├── agent/           #   Agent 系统（工具 + 技能）
│   │   └── ...
│   ├── scripts/admin.py     # 账号管理脚本（创建/重置/停用/列表）
│   └── tests/               # 77 个测试（含账号体系全流程）
├── frontend/web/            # 前端单页应用（原生 HTML/CSS/JS，由后端托管）
├── Dockerfile               # 网页服务镜像（无 Playwright）
└── docker-compose.yml       # 一键部署
```

---

## ✅ 测试

```bash
cd backend
python -m pytest tests/   # 77 passed
```

覆盖：注册/登录/修改密码/找回密码/重置密码/数据隔离/看板 CRUD/Agent 状态/统一响应信封。

## 📄 License

MIT License — 欢迎学习、使用、贡献。
