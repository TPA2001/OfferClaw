# 社区 + 岗位分享 实现方案

> 版本：v1.0 ｜ 日期：2026-08-28 ｜ 状态：待评审
> 关联模块：账号体系（JWT 多用户）、投递看板（applications）、Agent（LLM 预审）

## ✅ 实现状态（2026-08-28）

| 模块 | 状态 | 说明 |
|------|------|------|
| 数据模型 `models/community.py` | ✅ 已实现 | 5 张新表，create_all 自动创建，旧库升级数据零丢失（已验证） |
| 后端 API `api/community.py` | ✅ 已实现 | 18 个端点，含链接校验/限流/AI 预审/举报隐藏 |
| 前端视图 `views/community.js` / `job-shares.js` | ✅ 已实现 | 社区广场 + 网申广场，导航/路由/API 封装已接入 |
| 测试 `tests/test_community.py` | ✅ 已实现 | 20 个用例，全量 97 passed |
| M4 增强（Agent 岗位工具、分享者信誉分） | ⏳ 待做 | 后续迭代 |

安全能力已落地：http/https + 域名黑名单 + 内网/IP 直连拦截、按用户写操作限流、LLM 内容预审（Mock 降级放行）、举报达 3 次自动隐藏、LIKE 搜索转义、前端全量 esc() 防 XSS、对外仅暴露用户名。

---

## 一、背景与产品目标

当前 OfferCabin 是"个人求职管理工具"，用户与用户之间零交互，产品缺少两个增长引擎：

| 目标 | 解决的问题 | 商业价值 |
|------|-----------|---------|
| **社区** | 用户用完即走，无停留理由；简历优化等高频痛点无处交流 | 提升留存与活跃，形成 UGC 内容资产 |
| **岗位分享** | 网申信息分散在各官网，用户间信息不对称；单个用户覆盖面有限 | 用户互助产生网络效应，岗位库成为差异化数据资产 |

**核心设计原则：两个新模块必须与投递看板打通，不能做成孤岛。**

- 岗位分享页 → "一键加入我的看板"（复用 applications API）
- 社区讨论 → 可引用画像/看板数据（AI 辅助答疑）

---

## 二、产品设计

### 2.1 社区（求职广场）

**板块分类**（`category` 字段，前端 Tab 切换）：
- `resume` 简历优化
- `interview` 面试经验
- `offer` Offer 抉择
- `help` 求职求助
- `chat` 闲聊

**功能清单**：

| 功能 | 说明 | 优先级 |
|------|------|--------|
| 发帖 / 编辑 / 删除 | 作者可编辑删除；管理员可隐藏 | P0 |
| 评论（楼中楼） | 一级评论 + 二级回复（parent_id） | P0 |
| 点赞 / 收藏 | 统一 reaction 接口，幂等 | P0 |
| 浏览计数 | 详情页 +1，防刷（同一用户 5 分钟窗口只计一次） | P1 |
| 排序 | 最新 / 最热（热度 = 点赞×3 + 评论×5 + 浏览×0.1）/ 精华（置顶） | P1 |
| 搜索 | 标题 + 内容模糊搜索（LIKE） | P1 |
| 举报 | 违规内容举报，达阈值自动隐藏 | P0 |
| AI 预审 | 发帖时 LLM 判断是否含违规/广告内容，命中自动隐藏 | P1 |

**帖子状态机**：`normal → pinned（置顶）｜ hidden（违规/审核中）｜ deleted（删除）`

### 2.2 岗位分享（网申广场）

**分享字段**（表单）：

| 字段 | 必填 | 说明 |
|------|------|------|
| company | 是 | 公司名 |
| position | 是 | 岗位名 |
| apply_url | 是 | 网申官网链接（http/https） |
| city | 否 | 城市，如 北京/上海 |
| salary | 否 | 薪资范围，如 20-30k |
| deadline | 否 | 网申截止日期 |
| description | 否 | 备注（内推码、要求等） |

**功能清单**：

| 功能 | 说明 | 优先级 |
|------|------|--------|
| 分享 / 编辑 / 删除 | 作者可管理自己的分享 | P0 |
| 列表 + 筛选 | 按城市 / 即将截止（deadline < 7 天）/ 搜索 | P0 |
| 排序 | 最新 / 即将截止 / 最热 | P1 |
| **一键跳转官网** | 走后端 `redirect` 接口：校验链接 + 点击计数 + 302 跳转 | P0 |
| **一键加入看板** | 调 applications API 创建投递记录（预填 company/position/url） | P0 |
| 点赞 / 收藏 | 同社区 reaction 机制 | P1 |
| 过期标记 | 作者标记 / 系统按 deadline 自动标记 expired | P1 |
| 举报 / AI 预审 | 防垃圾链接与虚假岗位 | P0 |

---

## 三、数据模型

新建 `backend/app/models/community.py`，在 `main.py` 与 `models/__init__.py` 中 import（沿用现有 `Base.metadata.create_all` 自动建表机制，无需手动迁移）。

```
Post                                 Comment
─────────────────────                ─────────────────────
id            String(36) PK          id            String(36) PK
user_id       String(64) index       post_id       String(36) index
title         String(200)            user_id       String(64)
content       Text                   content       Text
category      String(30) index       parent_id     String(36) nullable  # 楼中楼
status        String(20) default normal  # normal/pinned/hidden/deleted
view_count    Integer default 0      created_at    DateTime
like_count    Integer default 0
comment_count Integer default 0      ─────────────────────
collect_count Integer default 0
created_at    DateTime
updated_at    DateTime

JobShare                             UserReaction（点赞/收藏统一表）
─────────────────────                ─────────────────────
id            String(36) PK          id            String(36) PK
user_id       String(64) index       user_id       String(64) index
company       String(200) index      target_type   String(20)  # post/jobshare
position      String(200)            target_id     String(36) index
apply_url     Text                   action        String(20)  # like/collect
city          String(50) nullable    created_at    DateTime
salary        String(100) nullable   Unique(user_id, target_type, target_id, action)
deadline      DateTime nullable index
description   Text nullable          Report
status        String(20) default normal  # normal/hidden/deleted/expired
view_count    Integer default 0     ─────────────────────
click_count   Integer default 0     id            String(36) PK
like_count    Integer default 0     user_id       String(64)
collect_count Integer default 0     target_type   String(20)
created_at    DateTime              target_id     String(36)
updated_at    DateTime              reason        String(200)
                                    status        String(20) default pending
                                    created_at    DateTime
```

**要点**：
- 沿用现有风格：`user_id` 字符串、不加外键约束、`_uuid_str()` 主键
- 社区/岗位内容**全站共享**（不加 user_id 过滤），`user_id` 仅用于归属与权限校验——这是与业务数据（按用户隔离）的关键差异，代码注释需显式说明
- 计数冗余字段（like_count 等）在 reaction 变更时同步更新，避免每次 COUNT 查询

---

## 四、API 设计

新建 `backend/app/api/community.py`，统一前缀 `/api/v1/community`，在 `main.py` 中 `app.include_router(community.router)`。沿用 `Depends(get_current_user)`、统一响应信封 `{code, message, data}`、`ok()` / `APIError`。

### 4.1 社区帖子

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | `/community/posts` | 发帖（触发 AI 预审） | 登录 |
| GET | `/community/posts` | 列表：`category` `sort=newest\|hot` `keyword` `page` `page_size` | 登录 |
| GET | `/community/posts/{post_id}` | 详情（浏览 +1） | 登录 |
| PUT | `/community/posts/{post_id}` | 编辑 | 作者 |
| DELETE | `/community/posts/{post_id}` | 删除（软删 status=deleted） | 作者/管理员 |
| POST | `/community/posts/{post_id}/comments` | 评论（`content` `parent_id?`） | 登录 |
| GET | `/community/posts/{post_id}/comments` | 评论列表（分页） | 登录 |
| DELETE | `/community/comments/{comment_id}` | 删除评论 | 作者/管理员 |

### 4.2 岗位分享

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | `/community/job-shares` | 分享岗位（链接校验 + AI 预审） | 登录 |
| GET | `/community/job-shares` | 列表：`city` `expiring=1` `keyword` `sort=newest\|hot\|deadline` | 登录 |
| GET | `/community/job-shares/{job_id}` | 详情（浏览 +1） | 登录 |
| GET | `/community/job-shares/{job_id}/redirect` | **跳转官网**：校验 status + 链接、click_count+1、返回 `{url}` 由前端 window.open | 登录 |
| POST | `/community/job-shares/{job_id}/to-application` | **一键加入看板**：创建 Application（company/position/job_url 预填，status=applied） | 登录 |
| PUT | `/community/job-shares/{job_id}` | 编辑 | 作者 |
| DELETE | `/community/job-shares/{job_id}` | 删除（软删） | 作者/管理员 |

### 4.3 统一互动与举报

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/community/reactions` | 点赞/收藏/取消：`{target_type, target_id, action, value:true\|false}`，幂等 |
| POST | `/community/reports` | 举报：`{target_type, target_id, reason}`，计数达 3 自动隐藏 |

**注意**：新增业务码必须同步补 `core/response.py` 的 `_CODE_TO_HTTP` 映射（如 40301 非作者、40404 帖子不存在），否则会回落 500。

---

## 五、前端设计

### 5.1 新增视图（`frontend/web/app/views/`）

- **`community.js`**：帖子列表页（分类 Tab + 排序 + 搜索框）→ 帖子详情页（正文 + 评论楼 + 点赞/收藏/举报）
- **`job-shares.js`**：岗位卡片流（筛选栏：城市/即将截止/搜索 + 排序）→ 详情弹窗 → 两个主按钮「去官网投递」「加入我的看板」

### 5.2 接入点（4 处修改）

1. **`index.html`**：侧边栏新增 `nav-section-label 互助社区` 分组，加两个 `nav-item`：
   - `data-route="/community"` 社区广场
   - `data-route="/job-shares"` 岗位分享
2. **`app/app.js`**：`registerViews()` 中注册 `/community`、`/job-shares` 路由
3. **`app/api.js`**：新增 `API.community = { listPosts, createPost, getPost, comment, react, report, listJobs, createJob, redirectJob, jobToApplication, ... }`，全部走 `API.API_V1`（禁止裸相对路径 fetch）
4. **`styles/main.css`**：补充卡片流、评论楼、分类 Tab 样式（沿用现有设计 token）

### 5.3 关键交互

- **一键跳转**：前端 `window.open(res.data.url, '_blank', 'noopener')`——统一走 redirect 接口而非直接渲染用户输入的 URL，杜绝 `javascript:` 等危险协议
- **一键加入看板**：成功后 toast「已加入看板」，按钮变「已在看板」状态；看板侧同步可跳回 `/kanban`
- **AI 预审被拦截**：帖子/岗位返回 `status=hidden` 且提示「内容审核中」，用户可见自己的内容但其他人不可见（避免误伤体验）

---

## 六、安全与风控（售卖场景硬要求）

| 风险 | 对策 | 优先级 |
|------|------|--------|
| 恶意/垃圾链接 | redirect 统一出口 + 仅允许 http/https + 域名黑名单（`core/community_safety.py`，可配） | P0 |
| 广告/违规内容 | LLM 预审（复用 Agent LLM 能力，无 Key 时规则降级：长度限制 + 敏感词表） | P1 |
| 垃圾刷帖 | 发帖/评论/分享频率限制（复用 `agent_rate_limit` 的限流模式，如 1 分钟 1 帖） | P0 |
| 刷点赞/浏览 | reaction 幂等（唯一约束）+ 浏览计数时间窗口 | P1 |
| 虚假岗位 | 举报阈值自动隐藏 + 分享者信誉分（被隐藏内容数 > 3 次禁发 7 天） | P2 |
| 隐私 | 社区仅展示用户名；不暴露邮箱/手机号；设置页说明 UGC 规则 | P0 |

---

## 七、与现有模块的联动（核心价值点）

```
岗位分享页                   投递看板
  │  一键加入看板                ▲
  ├─────────▶ applications ─────┘
  │          (预填 company/position/job_url)
  │
社区帖子 ──引用──▶ 简历画像/看板统计
  │              (Agent 在答疑时可读取用户上下文)
  ▼
Agent 助手 ──新增工具──▶ 岗位搜索/分享查询
```

- **后端**：`JobShare.to-application` 直接复用 applications 的内联 schema（`ApplicationCreate`），字段映射后创建，**无需改 applications.py**
- **Agent**：可选新增 2 个工具（`community_search_jobs` / `community_create_post`），让 Agent 能回答「社区最近有什么岗位分享」——低成本高感知
- **数据库**：新表由 `create_all` 自动创建，旧库无需迁移脚本（`auto_migrate` 只管补列，新表走 create_all）

---

## 八、里程碑与工作量

| 阶段 | 内容 | 预估 |
|------|------|------|
| **M1 后端** | community.py 模型 + API + 测试（CRUD/权限/reaction 幂等） | 3-5 天 |
| **M2 前端** | 社区页 + 岗位分享页 + 路由/导航/API 封装 | 3-5 天 |
| **M3 打通** | 一键加入看板 + redirect 跳转 + 限流/举报/链接校验 | 2-3 天 |
| **M4 增强** | AI 预审 + 热度排序 + 过期标记 + Agent 工具 | 2-3 天 |

**总计约 10-16 人日**，M1-M3 可先上线（对应 P0 功能），M4 增量迭代。

---

## 九、测试计划

- **单元测试**（`tests/test_community.py`，沿用 conftest 双 fixture）：
  - 发帖/编辑/删除的权限（非作者 40301）
  - reaction 幂等（重复点赞不重复计数）
  - 评论楼中楼 parent_id 校验
  - 举报阈值自动隐藏
  - 链接校验（拒绝 `javascript:`、非法域名）
  - `to-application` 正确创建 Application 且归属当前用户
- **集成链路**：分享岗位 → redirect 计数 → 一键加入看板 → 看板可见 → 社区详情可见

---

## 十、风险与开放问题

1. **UGC 内容安全**是最大风险（售卖场景被监管/被攻击的面）——先上规则 + 举报人工处理，AI 预审作为增强，不要作为唯一防线
2. **社区冷启动**：上线初期内置官方示例帖 + 种子岗位，管理员用 admin 脚本可批量发布
3. **岗位过期信息**：依赖用户维护 + deadline 自动标记，MVP 不做爬虫抓取（合规风险）
4. **是否允许匿名发帖**：开放问题，建议 MVP 实名（用户名），观察社区氛围后再决定
5. **管理员能力**：MVP 用 `scripts/admin.py` 扩展隐藏/置顶命令，Web 管理后台并入 P2 商业化阶段
