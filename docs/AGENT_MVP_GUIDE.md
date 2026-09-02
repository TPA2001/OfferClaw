# OfferCabin Agent MVP 使用指南

本指南介绍如何启动、使用、调试 OfferCabin Agent MVP。

## 目录

- [快速启动](#快速启动)
- [配置 LLM](#配置-llm)
- [使用 Agent](#使用-agent)
- [API 参考](#api-参考)
- [调试技巧](#调试技巧)
- [常见问题](#常见问题)

---

## 快速启动

### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt
playwright install chromium   # 智能填写需要
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，至少配置 DATABASE_URL
```

无 LLM API Key 也能启动，会自动降级使用 Mock Provider（基于关键词触发工具）。

### 3. 启动服务

```bash
# 后端（数据库表会在首次启动时自动创建）
python run.py

# 前端（新终端）
cd frontend/web
python -m http.server 3000
```

> Windows 用户必须使用 `python run.py` 而非 `uvicorn app.main:app`，
> 因为 `run.py` 会设置 ProactorEventLoop，Playwright 在 Windows 下依赖它创建子进程。

### 4. 访问 Agent

打开 http://localhost:3000/agent.html

---

## 配置 LLM

### 三种模式

#### 模式 A：Mock Provider（无需 API Key）

适合：本地调试、演示 Agent 框架

`.env` 留空 `OPENAI_API_KEY` 或显式设置：

```bash
LLM_PROVIDER=mock
```

Mock Provider 基于关键词识别用户意图并触发工具，能完成 80% 的基础操作（创建/查询/更新投递、查询统计），但不会真正生成自然语言回复。

#### 模式 B：OpenAI 官方

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

#### 模式 C：国内兼容服务（推荐国内用户）

**通义千问**（阿里云）：

```bash
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_MODEL=qwen-plus
```

**DeepSeek**：

```bash
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
```

**智谱 GLM**：

```bash
OPENAI_API_KEY=xxx
OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
OPENAI_MODEL=glm-4-flash
```

### 验证配置

启动后端后访问健康检查：

```bash
curl http://localhost:8000/health
```

查看日志：

```
INFO offercabin.llm.factory: 使用 OpenAI Provider
# 或
WARNING offercabin.llm.factory: 未配置 OPENAI_API_KEY，降级使用 Mock Provider
```

---

## 使用 Agent

### 前端界面

访问 `http://localhost:3000/agent.html`，看到对话界面。

**界面元素**：

- 顶部：会话切换栏（选择已有会话 / 新建）
- 中间：对话区，包含三类气泡
  - 蓝色（右）：用户消息
  - 浅蓝（左）：Agent 回复
  - 黄色：工具调用事件
  - 橙色卡片：敏感操作确认
- 底部：输入框（Enter 发送，Shift+Enter 换行）

### 示例对话

#### 示例 1：记录投递

```
用户：记录我投递了腾讯的后端开发岗位
Agent：好的，我来帮你记录...
       [🔧 create_application] 已记录投递：腾讯 - 后端开发
       已记录你投递腾讯后端开发岗位，状态为"已投递"，可以继续告诉我后续状态变化。
```

#### 示例 2：查询投递

```
用户：查看我的投递记录
Agent：[🔧 query_applications] 完成
       你目前有 3 条投递记录：
       1. 腾讯 - 后端开发（已投递）
       2. 阿里 - 算法工程师（面试中）
       3. 字节 - 客户端开发（笔试中）
```

#### 示例 3：更新状态

```
用户：腾讯进入面试了
Agent：[🔧 update_application_status] 腾讯 - 后端开发 状态变更：已投递 → 面试中
       已更新腾讯后端开发岗位的状态为"面试中"，加油！
```

#### 示例 4：查看统计

```
用户：我的投递统计概览
Agent：[🔧 get_dashboard_stats] 完成
       你的投递概览：
       - 总投递：5
       - 已投递：2
       - 笔试中：1
       - 面试中：1
       - 已录用：1
       - 回复率：80%
       - Offer率：20%
       - 平均等待：7.5 天
```

#### 示例 5：敏感操作（删除）

```
用户：删除腾讯的投递记录
Agent：[⚠️ 需要确认操作]
       工具：delete_application
       说明：删除一条投递记录...
       [确认执行] [取消]

用户点击"确认执行"

Agent：[🔧 delete_application] 已删除投递记录：腾讯 - 后端开发
       已删除腾讯后端开发的投递记录。
```

#### 示例 6：维护画像

```
用户：把我的求职意向城市改为上海和深圳
Agent：[🔧 update_profile] 画像已更新，更新字段: job_intent
       已更新你的求职意向城市为上海、深圳。
```

### 会话管理

- 每次发起新对话会创建会话，标题取自首条用户消息
- 切换会话可加载历史对话
- 会话持久化到数据库，重启服务不丢失

---

## API 参考

### POST /api/v1/agent/chat

SSE 流式对话。

**请求**：

```json
{
  "message": "记录我投递了腾讯后端",
  "session_id": null
}
```

**响应**：SSE 流，事件类型：

| 事件 | 字段 | 说明 |
|------|------|------|
| `content_delta` | `delta` | LLM 文本增量 |
| `tool_call_start` | `tool_call` | 工具调用开始（id/name/arguments） |
| `tool_result` | `tool_name` / `success` / `data` / `error` | 工具执行结果 |
| `confirm_required` | `action_id` / `tool_name` / `description` / `arguments` | 需要用户确认 |
| `done` | `session_id` / `finish_reason` | 任务完成 |
| `error` | `message` | 错误 |

**Curl 示例**：

```bash
curl -N -X POST http://localhost:8000/api/v1/agent/chat \
  -H "Authorization: Bearer demo-token" \
  -H "Content-Type: application/json" \
  -d '{"message": "查看我的投递", "session_id": null}'
```

### POST /api/v1/agent/confirm

确认敏感操作，恢复 Agent 执行。

**请求**：

```json
{
  "action_id": "action_abc123",
  "approved": true,
  "session_id": "uuid-of-session"
}
```

**响应**：SSE 流（同 chat）

### GET /api/v1/agent/sessions

列出当前用户的所有会话。

### GET /api/v1/agent/sessions/{session_id}

获取会话详情（含完整消息历史）。

### DELETE /api/v1/agent/sessions/{session_id}

删除会话。

---

## 调试技巧

### 1. 查看日志

后端日志按层级输出：

```
INFO offercabin.llm.factory: 使用 OpenAI Provider
INFO offercabin.agent.loop: Agent step 1/8
INFO offercabin.agent.tools.application_tools: 创建投递：腾讯 - 后端
INFO offercabin.agent.loop: Agent step 2/8
```

调整日志级别（在 `main.py` 顶部）：

```python
logging.basicConfig(level=logging.DEBUG)  # 改为 DEBUG 看更详细日志
```

### 2. Mock 模式调试

无 API Key 时用 Mock Provider，可以快速验证工具调用链路是否正常。Mock 会基于关键词触发工具，方便测试：

- "记录我投递了 XX 的 XX 岗位" → `create_application`
- "查看我的投递" → `query_applications`
- "XX 进入面试" → `update_application_status`
- "我的统计" → `get_dashboard_stats`
- "我的画像" → `get_profile`

### 3. 直接调用 API

跳过前端，用 curl 调试：

```bash
# 创建投递
curl -X POST http://localhost:8000/api/v1/agent/chat \
  -H "Authorization: Bearer demo-token" \
  -H "Content-Type: application/json" \
  -d '{"message": "记录我投递了美团算法岗"}'

# 查询
curl -X POST http://localhost:8000/api/v1/agent/chat \
  -H "Authorization: Bearer demo-token" \
  -H "Content-Type: application/json" \
  -d '{"message": "查看我的投递"}'
```

### 4. 检查数据库

```bash
sqlite3 backend/offercabin.db
```

```sql
.tables
SELECT * FROM applications;
SELECT id, title, created_at FROM agent_sessions;
SELECT id, messages FROM agent_sessions WHERE id = 'xxx';
```

### 5. 验证 LLM 配置

写个简单测试脚本 `test_llm.py`：

```python
import asyncio
from app.core.llm import get_default_provider, Message

async def main():
    llm = get_default_provider()
    resp = await llm.chat(messages=[
        Message(role="user", content="你好")
    ])
    print(resp.content)

asyncio.run(main())
```

运行：

```bash
cd backend
python test_llm.py
```

---

## 常见问题

### Q1：启动后 Agent 不响应？

检查：

1. 后端是否启动：访问 http://localhost:8000/health
2. CORS 是否配置正确（`main.py` 已配置 `allow_origins=["*"]`）
3. 浏览器控制台是否有报错

### Q2：Mock 模式下 Agent 只会返回"我能帮你..."？

Mock Provider 基于关键词匹配，必须包含特定关键词才能触发工具。建议使用以下模板：

- ✅ "记录我投递了 XX 的 XX 岗位"
- ✅ "查看我的投递记录"
- ✅ "XX 公司进入面试"
- ❌ "帮我把 XX 公司加到投递列表"（"投递列表"会触发 query 而非 create）

### Q3：OpenAI 模式下报 401？

检查 `OPENAI_API_KEY` 是否正确。日志会显示：

```
ERROR offercabin.llm.openai: OpenAI API HTTP 错误: 401 - ...
```

### Q4：国内访问 OpenAI 超时？

使用国内代理或国内兼容服务（通义千问/DeepSeek 等），见 [配置 LLM](#配置-llm)。

### Q5：删除操作点了确认没反应？

检查：

1. 网络请求是否成功（F12 → Network）
2. `action_id` 是否匹配
3. 后端日志是否有 `Agent 恢复运行异常`

### Q6：会话历史丢失？

会话在 `agent_sessions` 表持久化。检查：

1. 是否切换了 `DATABASE_URL`
2. SQLite 文件路径是否变化
3. `state.persist()` 是否执行（看日志）

### Q7：智能填写工具调用失败？

`extract_form_fields` 工具依赖 Playwright。首次使用需要：

```bash
playwright install chromium
```

且目标 URL 必须可访问。某些网站有反爬，可能抓取失败。

---

## 进阶：自定义系统提示词

编辑 `backend/app/agent/apps/job_agent.py` 中的 `JOB_AGENT_PROMPT`，调整 Agent 行为。

例如，希望 Agent 更主动地推荐操作：

```python
JOB_AGENT_PROMPT = """
你是 OfferCabin 求职助手。
...
## 行为准则
...
8. **主动建议**：每次工具调用后，根据结果主动给出下一步建议
   - 创建投递后 → 建议"是否要补充备注或简历版本？"
   - 状态变为面试后 → 建议"要不要我帮你准备面试题？"
"""
```

重启后端生效。

---

## 进阶：新增工具

以"搜索职位"工具为例：

### 1. 创建工具类

新建 `backend/app/agent/tools/job_search_tools.py`：

```python
from typing import Optional
from ..runtime.base_tool import BaseTool, ToolResult


class SearchJobsTool(BaseTool):
    name = "search_jobs"
    description = "搜索招聘网站的职位。当用户说'帮我找上海的后端岗位'时调用。"
    parameters = {
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "职位关键词"},
            "city": {"type": "string", "description": "城市（可选）"},
        },
        "required": ["keyword"],
    }

    def __init__(self, db, user_id):
        self.db = db
        self.user_id = user_id

    async def execute(self, keyword: str, city: Optional[str] = None) -> ToolResult:
        # TODO: 调用真实招聘 API
        return ToolResult(success=True, data={
            "jobs": [
                {"company": "示例公司", "position": keyword, "city": city or "不限"},
            ],
            "count": 1,
        })
```

### 2. 注册工具

编辑 `backend/app/agent/apps/job_agent.py`：

```python
from app.agent.tools import ...  # 现有工具
from app.agent.tools.job_search_tools import SearchJobsTool  # 新增

def create_job_agent(...):
    registry = ToolRegistry()
    # ... 现有工具
    registry.register(SearchJobsTool(db, user_id))   # 新增
    ...
```

### 3. 验证

重启后端，对话：

```
用户：帮我找上海的后端岗位
Agent：[🔧 search_jobs] 完成
       为你找到以下上海的后端岗位：
       ...
```

LLM 会自动识别意图并调用新工具，无需修改其他代码。

---

## 总结

OfferCabin Agent MVP 实现了：

- ✅ 三层解耦架构（LLM / Runtime / App）
- ✅ 多 Provider 支持（OpenAI 兼容 + Mock 降级）
- ✅ 流式输出（SSE）
- ✅ 工具调用循环
- ✅ 敏感操作确认机制
- ✅ 会话持久化
- ✅ 9 个业务工具覆盖核心场景
- ✅ 完整前端对话面板

下一步建议：

1. 配置真实 LLM API Key，体验完整的自然语言对话
2. 根据实际使用反馈调整系统提示词
3. 参照"扩展指南"添加新工具（如职位搜索、简历优化）
4. 阅读 [AGENT_ARCHITECTURE.md](./AGENT_ARCHITECTURE.md) 了解架构细节
