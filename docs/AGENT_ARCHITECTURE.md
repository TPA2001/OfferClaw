# OfferClaw Agent 架构设计

本文档描述 OfferClaw 的 Agent 化架构，参考 [Pi Agent Harness](https://github.com/earendil-works/pi) 的核心思想，针对求职管理场景做了三层解耦设计。

## 目录

- [设计哲学](#设计哲学)
- [整体架构](#整体架构)
- [LLM 抽象层](#llm-抽象层)
- [Agent Runtime](#agent-runtime)
- [工具层](#工具层)
- [应用层](#应用层)
- [数据流](#数据流)
- [与 Pi 的对比](#与-pi-的对比)
- [扩展指南](#扩展指南)

---

## 设计哲学

Pi 的核心思想是把 Agent 拆成三个相互独立的层次，让每一层都能单独演进：

1. **LLM 抽象层**（`pi-ai`）：屏蔽 provider 差异，提供统一 chat / tool calling 接口
2. **Agent Runtime**（`pi-agent-core`）：实现 Agent 循环引擎、状态管理、工具调用
3. **应用层**（`pi-coding-agent`）：定义具体场景的系统提示词、工具集、行为准则

OfferClaw 沿用这个三层模型，但根据求职管理场景做了以下适配：

| 维度 | Pi | OfferClaw |
|------|----|----|
| 部署形态 | 本地 CLI | Web + 浏览器扩展 |
| 状态持久化 | 文件系统 | SQLite |
| 流式输出 | 终端 TUI | SSE + 浏览器 |
| 权限边界 | 容器化沙盒 | 用户确认 + 敏感数据本地 |
| Agent 形态 | 通用编码助手 | 求职管理专精 |

---

## 整体架构

```
┌──────────────────────────────────────────────────────┐
│  前端  frontend/web/agent.html                       │
│  对话面板 · 工具调用气泡 · 确认卡片 · 会话切换       │
├──────────────────────────────────────────────────────┤
│  HTTP / SSE                                           │
├──────────────────────────────────────────────────────┤
│  API 层  app/api/agent.py                            │
│  POST /chat · POST /confirm · GET /sessions          │
├──────────────────────────────────────────────────────┤
│  应用层  app/agent/apps/job_agent.py                 │
│  系统提示词 + 工具注册                                │
├──────────────────────────────────────────────────────┤
│  Agent Runtime  app/agent/runtime/                   │
│  loop · state · registry · base_tool · events        │
├──────────────────────────────────────────────────────┤
│  LLM 抽象层  app/core/llm/                           │
│  base · openai_provider · mock_provider · factory    │
├──────────────────────────────────────────────────────┤
│  工具层  app/agent/tools/                            │
│  profile · application · dashboard · smart_fill      │
├──────────────────────────────────────────────────────┤
│  业务层  app/models · app/services · app/automation  │
│  Profile · Application · AgentSession · SmartFill    │
└──────────────────────────────────────────────────────┘
```

---

## LLM 抽象层

**位置**：`backend/app/core/llm/`

对应 Pi 的 `pi-ai` 包。统一多 provider 接口，让 Agent 代码不感知底层是 OpenAI / Anthropic / 通义千问 / 还是 Mock。

### 核心抽象

```python
# base.py
class LLMProvider(ABC):
    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """同步返回完整响应"""

    async def chat_stream(...):
        """流式输出，yield 事件字典"""
```

### 标准化数据结构

- `Message`：统一消息（system/user/assistant/tool），自带 `to_dict()` 适配各 provider
- `ToolCall`：`id` + `name` + `arguments`（dict）
- `ToolSchema`：OpenAI function calling 格式
- `LLMResponse`：`content` + `tool_calls` + `finish_reason` + `usage`
- `TokenUsage`：token 计数

### 已实现的 Provider

| Provider | 文件 | 适用场景 |
|----------|------|---------|
| `OpenAIProvider` | `openai_provider.py` | OpenAI 官方 / 国内代理 / 通义千问 / DeepSeek 等所有兼容 OpenAI 协议的服务 |
| `MockProvider` | `mock_provider.py` | 无 API Key 时降级使用，基于关键词触发工具，便于本地调试 |

### Provider 工厂

```python
# factory.py
def get_default_provider() -> LLMProvider:
    if os.getenv("OPENAI_API_KEY"):
        return OpenAIProvider()
    return MockProvider()  # 降级
```

### 配置

通过环境变量控制：

```bash
LLM_PROVIDER=openai                # openai / mock
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

切换 provider 不需要改业务代码，只改环境变量。

---

## Agent Runtime

**位置**：`backend/app/agent/runtime/`

对应 Pi 的 `pi-agent-core` 包。这是整个 Agent 系统的核心。

### 核心组件

#### `BaseTool`（`base_tool.py`）

所有工具的基类：

```python
class BaseTool(ABC):
    name: str
    description: str
    parameters: dict            # JSON Schema
    requires_confirmation: bool = False

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        ...

    def to_schema(self) -> ToolSchema:
        # 转换为 LLM 可识别的工具定义
```

#### `ToolResult`（`base_tool.py`）

工具执行结果，含 `success` / `data` / `error` / `requires_confirmation` / `pending_action_id` 五个字段。`to_message_content()` 方法把结果序列化为字符串，作为 tool 消息回传给 LLM。

#### `ToolRegistry`（`registry.py`）

工具注册中心：

```python
registry = ToolRegistry()
registry.register(GetProfileTool(db, user_id))
registry.register(CreateApplicationTool(db, user_id))
# ...

schemas = registry.schemas()       # 传给 LLM
tool = registry.get("create_application")
```

#### `AgentState`（`state.py`）

会话状态管理，职责：

- 维护消息历史（含 system prompt）
- 持久化到 `agent_sessions` 表（JSON 序列化）
- 上下文超长时自动压缩（保留 system + 最近 20 条）
- 管理待确认的敏感操作（`pending_actions`）

关键方法：

```python
state.add_user(content)
state.add_assistant(content=None, tool_calls=[...])
state.add_tool_result(tool_call_id, name, content)
state.persist()    # 写库
state.compress()   # 压缩历史
```

#### `AgentLoop`（`loop.py`）

Agent 循环引擎，执行流程：

```
1. 用户输入 → 加入 state
2. while step < max_steps:
     a. 调用 LLM（带工具定义、流式）
     b. 累积 content + tool_calls
     c. 加入 assistant 消息
     d. 若无 tool_calls → 完成，return
     e. 依次执行 tool_calls：
        - 需要 confirmation → 发 ConfirmRequiredEvent，挂起
        - 否则 → 执行工具，结果加入 state
     f. 继续下一轮 LLM 调用
3. 持久化 state
```

支持两种入口：

- `run_stream(user_input)`：首次对话
- `resume_after_confirm(action_id, approved)`：用户确认敏感操作后恢复

### 流式事件（`events.py`）

所有事件继承 `AgentEvent`，通过 SSE 推送前端：

| 事件类型 | 含义 |
|---------|------|
| `ContentDelta` | LLM 文本增量 |
| `ToolCallStart` | 工具调用开始 |
| `ToolResultEvent` | 工具执行结果 |
| `ConfirmRequiredEvent` | 需要用户确认 |
| `DoneEvent` | 任务完成 |
| `ErrorEvent` | 错误 |

---

## 工具层

**位置**：`backend/app/agent/tools/`

封装业务能力为 agent 可调用的工具。每个工具声明 JSON Schema，LLM 通过 function calling 自动选择。

### 工具清单

| 工具名 | 文件 | 说明 | 需确认 |
|--------|------|------|--------|
| `get_profile` | `profile_tools.py` | 获取用户画像 | 否 |
| `update_profile` | `profile_tools.py` | 更新用户画像 | 否 |
| `create_application` | `application_tools.py` | 创建投递记录 | 否 |
| `update_application_status` | `application_tools.py` | 更新投递状态 | 否 |
| `query_applications` | `application_tools.py` | 查询投递列表 | 否 |
| `delete_application` | `application_tools.py` | 删除投递记录 | **是** |
| `get_dashboard_stats` | `dashboard_tools.py` | 看板统计概览 | 否 |
| `extract_form_fields` | `smart_fill_tools.py` | 从 URL 提取表单字段 | 否 |
| `match_fields_to_profile` | `smart_fill_tools.py` | LLM 语义匹配 | 否 |

### 状态机

投递记录的状态流转：

```
applied (已投递)
   ├──→ assessment (笔试中)
   │       └──→ interview (面试中)
   │               ├──→ offer (已录用) ✓
   │               └──→ rejected (已拒绝) ✗
   ├──→ rejected (已拒绝) ✗
   └──→ withdrawn (已撤回)
```

工具层通过 `VALID_STATUSES` 字典约束合法状态值，LLM 必须用英文枚举值调用。

---

## 应用层

**位置**：`backend/app/agent/apps/job_agent.py`

对应 Pi 的 `pi-coding-agent` 包。定义求职主 Agent 的系统提示词、工具组合、行为准则。

### 系统提示词

`JOB_AGENT_PROMPT` 包含：

- Agent 能力说明
- 行为准则（多步规划、信息查询、敏感操作、隐私保护、回复风格）
- 状态值规范
- 回复风格要求

### 工厂函数

```python
def create_job_agent(
    llm: LLMProvider,
    db: Session,
    user_id: str,
    session_id: str | None = None,
    max_steps: int = 8,
) -> AgentLoop:
    registry = ToolRegistry()
    registry.register(GetProfileTool(db, user_id))
    registry.register(UpdateProfileTool(db, user_id))
    # ... 注册所有工具

    state = AgentState(db=db, user_id=user_id, session_id=session_id)
    return AgentLoop(llm, registry, JOB_AGENT_PROMPT, state, max_steps)
```

---

## 数据流

### 典型对话流：用户说"记录我投递了腾讯的后端岗位"

```
1. 前端 POST /api/v1/agent/chat  { message: "记录我投递了腾讯的后端岗位" }

2. API 层
   - get_default_provider() → OpenAIProvider 或 MockProvider
   - create_job_agent(llm, db, user_id) → AgentLoop 实例
   - StreamingResponse 包装 SSE

3. AgentLoop.run_stream("...")
   - state.add_user(message)
   - 进入循环：
     a. LLM.chat_stream(messages, tools=schemas)
        → 流式返回 tool_call: create_application(company="腾讯", position="后端")
        → 前端收到 ContentDelta("好的，我来帮你记录...")
        → 前端收到 ToolCallStart
     b. 执行 CreateApplicationTool.execute(company="腾讯", position="后端")
        → 数据库插入 Application 记录
        → 返回 ToolResult(success=True, data={...})
     c. state.add_tool_result(...)
     d. 前端收到 ToolResultEvent(success=True, data={message: "已记录投递：腾讯 - 后端"})
   - 第二轮 LLM 调用（带 tool 结果）
     → LLM 看到工具成功，生成最终回复："已记录你投递腾讯后端岗位，状态为'已投递'..."
     → 前端收到 ContentDelta
     → 无 tool_call，循环结束
   - state.persist() → 写入 agent_sessions 表
   - 前端收到 DoneEvent(session_id=xxx)
```

### 敏感操作流：用户说"删除腾讯的投递记录"

```
1-3. 同上，LLM 调用 delete_application
4. AgentLoop 检测到 tool.requires_confirmation == True
   - 生成 action_id，存入 state.pending_actions
   - 发送 ConfirmRequiredEvent(action_id, tool_name, description, arguments)
   - ToolResult 包含 requires_confirmation=True，不实际执行删除
5. LLM 看到工具结果"待确认"，生成回复"删除操作需要你确认..."
6. 循环结束，state 持久化（含 pending_action）

7. 前端收到 ConfirmRequiredEvent，渲染确认卡片
   - 用户点"确认" → POST /api/v1/agent/confirm { action_id, approved=true, session_id }
8. AgentLoop.resume_after_confirm(action_id, true)
   - 从 state 取出 pending_action
   - 执行 DeleteApplicationTool.execute(...)
   - 加入 tool_result
   - 继续下一轮 LLM 调用 → 生成"已删除..."回复
```

---

## 与 Pi 的对比

| 方面 | Pi | OfferClaw |
|------|----|----|
| LLM 抽象 | `pi-ai` 支持 OpenAI/Anthropic/Google 等 | `app/core/llm/` 支持 OpenAI 兼容 + Mock |
| Agent Loop | `pi-agent-core` | `app/agent/runtime/loop.py` |
| 应用层 | `pi-coding-agent`（编码场景） | `app/agent/apps/job_agent.py`（求职场景） |
| 工具调用 | OpenAI function calling 协议 | 同 |
| 流式输出 | 终端 TUI 渲染 | SSE 推送到浏览器 |
| 状态持久化 | 文件系统（JSON） | SQLite（agent_sessions 表） |
| 权限控制 | 容器化沙盒 | `requires_confirmation` 标记 + 用户确认 |
| 自扩展 | Agent 可生成新工具 | MVP 未实现，预留接口 |

### 关键借鉴点

1. **三层解耦**：LLM / Runtime / App 分离，每层可独立替换
2. **工具即能力**：Agent 能力由注册的 tools 决定，扩展只需新增工具
3. **流式优先**：所有 LLM 调用走流式，用户体验更好
4. **标准化协议**：用 OpenAI function calling 作为工具定义的事实标准

---

## 扩展指南

### 新增 LLM Provider

1. 继承 `LLMProvider`，实现 `chat()` 和 `chat_stream()`
2. 在 `factory.py` 注册
3. 通过环境变量切换

### 新增工具

1. 继承 `BaseTool`，定义 `name` / `description` / `parameters` / `execute()`
2. 在 `job_agent.py` 的 `create_job_agent()` 中 `registry.register()`
3. 自动被 LLM 识别和调用

示例：

```python
class SearchJobsTool(BaseTool):
    name = "search_jobs"
    description = "搜索招聘网站的职位"
    parameters = {
        "type": "object",
        "properties": {
            "keyword": {"type": "string"},
            "city": {"type": "string"},
        },
        "required": ["keyword"],
    }

    def __init__(self, db, user_id):
        self.db = db
        self.user_id = user_id

    async def execute(self, keyword: str, city: str = None) -> ToolResult:
        # 调用 Boss 直聘 / 拉勾 API
        ...
        return ToolResult(success=True, data={"jobs": [...]})
```

### 新增 Agent 应用

未来可以创建不同场景的 Agent（如"面试准备 Agent"、"简历优化 Agent"）：

1. 在 `app/agent/apps/` 新建文件
2. 定义专属系统提示词和工具子集
3. 新建 API 路由

---

## 后续演进路线

### Phase 2（已规划）

- Agent 工具自扩展：让 Agent 自己生成工具代码并注册
- 多 Agent 协作：求职主 Agent 调用子 Agent（如简历优化 Agent）
- 上下文压缩优化：摘要式压缩而非简单丢弃
- 工具调用结果可视化：在前端展示结构化数据

### Phase 3

- 浏览器扩展集成：Agent 直接操作扩展完成表单填写
- 任务调度：定时执行"检查投递状态"等任务
- 多用户隔离：完善 user_id 边界

### Phase 4

- Agent 评估：自动评估 Agent 决策质量
- 工具调用审计：记录所有工具调用，便于回放和调试
- A/B 测试：不同系统提示词效果对比
