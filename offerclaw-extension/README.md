# OfferClaw 浏览器扩展（V0.0.3）

OfferClaw 官方 Chrome MV3 扩展。在用户已登录的真实浏览器中扫描网申表单 → 调 OfferClaw 后端匹配（隐私优先）→ 在真实 DOM 上确定性填写。同时提供投递记录、用户画像、敏感数据本地管理。

> 本扩展为 OfferClaw 项目的一部分，采用 MIT 协议。

## 功能

1. **表格填充**：扫描当前页表单字段 → 后端 `/automation/ext/match` 匹配 → 本地 `fill-runtime` 确定性填写（兼容 React/Vue 受控组件），不自动提交。
2. **投递记录**：本地 `chrome.storage.local` 维护看板副本（与后端 `/applications` 解耦，零依赖可用）。
3. **数据库持久化**：`chrome.storage.local` + 版本号 + `migrate()`，扩展版本升级后数据依然可用。
4. **用户画像**：本地画像（V0.0.3 支持一键从后端 `/api/v1/profiles/` 同步）。
5. **LLM 隐私**：默认规则匹配（PII 不出后端内存）；可选 LLM 时后端对姓名/手机/邮箱/出生脱敏后再调用。

## 隐私设计

| 数据 | 存放位置 | 说明 |
|------|---------|------|
| 非敏感画像（教育/工作/技能/项目） | OfferClaw 后端 | Agent 可读写，扩展可查看 |
| PII（姓名/手机/邮箱/出生） | 后端内存（规则匹配）/ 脱敏后发 LLM（LLM 模式） | LLM 永不接触真实 PII |
| 敏感数据（身份证/住址/银行卡/护照） | **扩展本地** `chrome.storage.local` | 后端永不接触，填写时本地注入 |

扩展**不直接调用任何第三方 LLM**。所有匹配经 OfferClaw 后端 `/automation/ext/match`：
- `use_llm=false`（默认）：纯规则匹配，不调 LLM，零隐私泄露、免 API Key、免订阅。
- `use_llm=true`：后端对画像 PII 与字段 `current_value` 中的 PII 脱敏为占位符（如 `[REDACTED_PHONE]`），LLM 只看到占位符，返回后由后端还原真实值。

## 安装

1. 打开 Chrome → `chrome://extensions` → 开启「开发者模式」。
2. 「加载已解压的扩展程序」→ 选择 `offerclaw-extension/` 目录。
3. 扩展图标出现在工具栏，点击打开侧边弹窗。

## 后端准备（DEV 模式，跳过收费）

内测阶段后端为 open 鉴权（无 token）。但 `main.py` 的 license 门控中间件会拦截未激活请求，扩展端点需 DEV 模式放行：

```powershell
# Windows PowerShell
$env:OFFERCLAW_DEV="1"
# 启动后端
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

在扩展「设置」面板填后端地址（默认 `http://localhost:8000`），点「测试连接」应显示「后端已连接」。

## 使用流程

### 智能填写
1. 打开网申表单页（确保已登录）。
2. 点扩展图标 → 「填写」面板。
3. （可选）勾选「LLM 增强匹配」。
4. 点「扫描并智能填写」。字段会被高亮：绿=已填、黄=待确认、灰=跳过。
5. 人工核对后自行提交。

### 投递记录
- 「投递」面板：查看/过滤/改状态。新建投递时若不填链接，自动取当前网申页地址。

### 画像与同步
- 「画像」面板查看本地画像完成度。
- 「设置」面板填写身份证/住址/银行卡/护照（仅存本地），填写时自动注入对应字段。
- **V0.0.3 新增「从后端同步画像」**：开启后端后，popup 启动时自动从 `/api/v1/profiles/` 拉取 Web 端填的画像并合并到本地；「画像」面板可手动触发再次同步。合并策略：远端非空字段覆盖本地空字段，本地非空值保留（双向择优）。

## 数据持久化与迁移

- 单一存储键 `offerclaw_db`（`chrome.storage.local`），含 `version` 字段。
- `shared/storage.js` 的 `migrate()` 按 `version` 逐级升级，保留已有数据。
- 升级扩展后首次运行自动迁移并回写。
- 「设置 → 导出」可备份全部本地数据为 JSON；「重置」清空回默认。

## 文件结构

```
offerclaw-extension/
├── manifest.json           # MV3 配置
├── background.js           # service worker（迁移/消息路由）
├── content.js              # 页面扫描+填写注入
├── content.css             # 填写视觉反馈
├── popup.html/css/js       # 侧边弹窗 UI（填写/投递/画像/设置）
└── shared/
    ├── schema.js           # 数据结构与常量
    ├── storage.js          # 持久化层 + 版本迁移
    ├── config.js           # 后端配置
    ├── privacy.js          # 本地敏感字段识别
    ├── scanner.js          # 表单字段扫描器
    ├── fill-runtime.js     # 确定性填写运行时
    ├── api-client.js       # 后端 API 客户端
    ├── profile-matcher.js  # 规则匹配引擎（无后端依赖）
    └── profile-sync.js     # 后端画像 → 本地画像 同步
```

## 对接的后端端点

| 端点 | 用途 |
|------|------|
| `POST /api/v1/automation/ext/match` | 扩展专用匹配（隐私优先，skip_subscription） |
| `GET /api/v1/profiles/` | 获取画像 |
| `GET /api/v1/profiles/completion` | 画像完成度 |
| `GET/POST /api/v1/applications/` | 投递记录 CRUD |
| `PATCH /api/v1/applications/{id}/status` | 改投递状态 |
| `GET /health` | 后端健康检查 |

## V0.0.3 变更

- 新增「从后端同步画像」：popup 启动时自动同步（满足「从未同步 / 超过 10 分钟 / 本地空」任一条件触发），并提供手动同步按钮。
- 新增 `shared/profile-sync.js`：后端 → 本地字段映射 + 双向择优合并。
- popup 画像面板新增「数据来源」与「最近同步时间」展示。
- 修复：扩展"启用后端"后无法加载用户信息的问题（后端画像未拉取到本地）。

## V0.0.1/0.0.2 限制

- 仅内测，不自动提交表单。
- 文件上传字段（简历附件）仅标记 `FILE:resume`，不自动上传。
- 映射缓存按页面结构签名，TTL 24h。
- 多步骤向导需逐页点击填写。
