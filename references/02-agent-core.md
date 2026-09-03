# Agent 核心用法

## 1. 最小 Agent

```python
from agno.agent import Agent
from agno.models.openai import OpenAIResponses

assistant = Agent(
    id="assistant",
    name="Assistant",
    model=OpenAIResponses(id="gpt-5.5"),
    instructions=[
        "先直接回答，再给必要依据。",
        "事实不确定时明确说明，不得编造。",
    ],
    markdown=True,
)

assistant.print_response("解释什么是 AgentOS", stream=True)
```

模型 ID 只是示例。部署时从配置读取并验证该模型是否支持所需能力。

## 2. Agent 构造原则

稳定配置放构造器：

- `id`, `name`, `description`, `role`
- `model`, `reasoning_model`, fallback model
- `instructions`
- `tools`, `skills`, `knowledge`
- `db`, memory manager
- `input_schema`, `output_schema`
- hooks、guardrails、tool limits、compression

请求特定数据放运行参数：

- message/input
- `user_id`
- `session_id`
- `session_state`
- dependencies/context
- files/images/audio/video
- metadata

不要通过修改共享 Agent 的字段来注入某个用户的数据；并发请求会相互覆盖。

## 3. 稳定 ID

显式设置 `id`：

```python
agent = Agent(id="support-agent-v1", name="Support Agent", ...)
```

`id` 会影响 API path、组件识别、Session 查询、RBAC scope 和可观测性。展示名称可以变化，机器 ID 应尽量稳定。

## 4. Sync、Async 与 Streaming

### Sync

```python
run = agent.run(
    "Summarize my account",
    user_id="u_123",
    session_id="support_456",
)
print(run.content)
```

### Async

```python
run = await agent.arun(
    "Summarize my account",
    user_id="u_123",
    session_id="support_456",
)
```

### Streaming

终端可用：

```python
agent.print_response("Hello", stream=True)
```

自定义服务中迭代事件时，应依据当前 Agno `RunEvent` 类型处理，而不是拼接所有 event 字段。AgentOS 已提供 SSE 时，优先使用内建 endpoint。

服务端原则：

- 请求 handler 使用 `await agent.arun(...)`；
- 外部同步 SDK 需放线程池或换异步客户端；
- 不在 async handler 中调用阻塞 I/O；
- stream 断开不代表 run 必然取消，按产品需要提供 cancel/resume。

## 5. Instructions 的工程写法

推荐包含：

1. 角色与目标；
2. 事实来源优先级；
3. 工具选择规则；
4. 处理步骤；
5. 输出格式；
6. 缺失数据与失败行为；
7. 安全与权限边界；
8. 长度、语气等表现要求。

示例：

```python
instructions = [
    "你是订单查询助手，只回答调用者有权访问的订单。",
    "涉及订单状态时必须调用 get_order；不要根据聊天历史猜测。",
    "调用工具前确认 order_id 格式。",
    "工具返回 not_found 时明确说未找到，不得虚构替代订单。",
    "修改订单只能调用需要确认的 write tool。",
    "最终输出包含 status、next_action 和简短解释。",
]
```

安全约束不能只写 prompt，工具本身还要做身份与资源归属校验。

## 6. 结构化输出

```python
from typing import Literal

from pydantic import BaseModel, Field


class SupportAnswer(BaseModel):
    answer: str
    confidence: float = Field(ge=0, le=1)
    status: Literal["resolved", "needs_user", "escalate"]
    cited_record_ids: list[str] = Field(default_factory=list)


agent = Agent(
    id="support",
    model=model,
    tools=[get_order],
    output_schema=SupportAnswer,
)

run = agent.run(
    "Where is order 123?",
    user_id="u_1",
    session_id="s_1",
)
answer: SupportAnswer = run.content
```

原则：

- 使用 `Literal`/Enum 限制状态；
- 可缺失事实用 `Optional`，不要要求模型编造；
- 字段写 description、范围、长度；
- 不把大型原始文档塞进输出；
- schema validation 失败要记录并评测；
- 事实仍由工具/Knowledge 验证。

## 7. 结构化输入

对 Workflow 或复杂 Agent 输入，使用 `input_schema`。即使 API 接收文本，也可以先由普通代码解析和验证关键业务字段，再交给 Agent。

```python
class TicketInput(BaseModel):
    ticket_id: str = Field(pattern=r"^T-[0-9]+$")
    action: Literal["summarize", "draft_reply"]
```

不要让 LLM 负责验证数据库主键、金额精度、法定日期或权限 token。

## 8. 会话历史

```python
agent = Agent(
    db=db,
    add_history_to_context=True,
    num_history_runs=5,
)
```

`add_history_to_context` 决定是否把历史送入本次模型上下文；DB 持久化和上下文注入是两回事。历史太长时：

- 限制 `num_history_runs`；
- 使用 Session summary；
- 对工具结果使用 compression；
- 将稳定事实转入结构化 state 或 memory；
- 不要每轮全量回放。

## 9. Past Session Search

v3 参数为：

```python
agent = Agent(
    db=db,
    search_past_sessions=True,
    num_past_sessions_to_search=3,
    num_past_session_runs_in_search=5,
)
```

这不是 Memory 的替代品。它是搜索过往对话；要限制范围，防止把无关旧线程引入当前决策。

## 10. Reasoning Model

v3 不再使用 `reasoning=True` 捷径。显式配置：

```python
agent = Agent(
    model=answer_model,
    reasoning_model=reasoning_model,
)
```

只在评测显示收益时启用。额外 reasoning model 会增加延迟与成本，也可能使工具链复杂化。

## 11. Fallback 与重试

模型 fallback 用于 provider outage、rate limit 或特定模型错误，不用于掩盖错误 prompt/工具：

```python
agent = Agent(
    model=primary_model,
    fallback_models=[backup_model],
)
```

实际字段和 provider 行为需按安装版本核验。注意：

- fallback 模型必须支持相同工具/结构化输出能力；
- provider 间 tool-call ID、system role 和 multimodal 支持可能不同；
- 记录发生 fallback 的次数；
- 写工具执行后不得因模型 fallback 重复执行 side effect。

Provider client retry 与 Agent tool-loop retry是不同层。重试前先判断操作是否幂等。

## 12. Context Compression

搜索和数据工具返回大量结果时：

```python
agent = Agent(
    model=model,
    tools=[search_tool],
    compress_tool_results=True,
)
```

压缩会增加额外模型调用，应评测总 token、延迟和事实保真。数值、日期、实体、URL 是重点回归项。

## 13. 生命周期与并发

正确：

```python
# module scope
agent = Agent(...)

@app.post("/ask")
async def ask(request: Request):
    identity = request.state.identity
    return await agent.arun(
        request.message,
        user_id=identity.user_id,
        session_id=request.session_id,
    )
```

错误：

```python
@app.post("/ask")
async def ask(request):
    agent = Agent(...)  # 每个请求重建
    return await agent.arun(request.message)
```

自定义工具类不要用实例变量保存“当前用户”或“当前 Session”。使用 `RunContext`/依赖注入或函数参数。
