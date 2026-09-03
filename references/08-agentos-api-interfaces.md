# AgentOS：服务化、REST、SSE、MCP 与接口

## 1. AgentOS 的职责

`AgentOS` 是 Agno 的生产运行时与 API 层。它把长期复用的 `Agent`、`Team`、`Workflow` 和 `Knowledge` 注册为服务，并统一提供：

- FastAPI 应用；
- REST 与流式事件；
- Session、Run、Memory、Knowledge 等管理接口；
- 可选 MCP、A2A、AG-UI、Slack 等接口；
- JWT/RBAC、用户隔离；
- Tracing、Evals、Metrics；
- Background run、Queue、Scheduler；
- AgentOS UI / Control Plane 的配置发现。

不要把 AgentOS 当作业务后端的全部。订单、支付、订阅、额度、设备归属、合规资料等仍属于普通业务服务和数据库。

## 2. 最小可运行服务

```python
from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.openai import OpenAIResponses
from agno.os import AgentOS


db = SqliteDb(
    id="local-db",
    db_file="tmp/agentos.db",
)

assistant = Agent(
    id="assistant",
    name="Assistant",
    model=OpenAIResponses(id="gpt-5.5"),
    db=db,
    instructions="Answer accurately and state uncertainty.",
    add_history_to_context=True,
    num_history_runs=5,
)

agent_os = AgentOS(
    id="example-agent-os",
    description="Example AgentOS",
    db=db,
    agents=[assistant],
    tracing=True,
)

app = agent_os.get_app()

if __name__ == "__main__":
    agent_os.serve(app="app:app", host="0.0.0.0", port=7777, reload=True)
```

开发时可打开：

```text
GET /health
GET /config
GET /docs
GET /openapi.json
```

生产中关闭 `reload`，并由进程管理器或容器平台启动。

## 3. AgentOS 构造参数的工程分组

当前 `AgentOS` 常用参数可按职责理解：

### 组件注册

```python
AgentOS(
    db=db,
    agents=[assistant],
    teams=[research_team],
    workflows=[publish_workflow],
    knowledge=[product_knowledge],
)
```

没有自带 DB 的组件可继承 AgentOS 的默认 `db`。生产中仍建议组件关系清楚，不要把多个互不相关业务域全部塞进一个巨大 AgentOS。

### 服务表面

```python
AgentOS(
    cors_allowed_origins=["https://app.example.com"],
    interfaces=[...],
    a2a_interface=False,
    mcp=False,
)
```

### 安全

```python
AgentOS(
    authorization=True,
    authorization_config=authorization_config,
)
```

### 运维

```python
AgentOS(
    tracing=True,
    queue=queue_config,
    scheduler=True,
    event_stream=event_stream,
    telemetry=False,
)
```

### 扩展 FastAPI

```python
AgentOS(
    base_app=custom_fastapi_app,
    on_route_conflict="error",
    lifespan=lifespan,
)
```

`on_route_conflict="error"` 适合 CI/生产，避免自定义路由静默覆盖 AgentOS 路由。

## 4. 调用 Agent 的 REST 形态

Agent run 的主要服务路径形态为：

```text
POST /agents/{agent_id}/runs
```

AgentOS 的 run 请求通常使用 `multipart/form-data`，因为同一接口需要兼容消息、图片、音频和文件。纯文本示例：

```bash
curl -N -X POST 'http://localhost:7777/agents/assistant/runs' \
  -H 'Authorization: Bearer YOUR_JWT' \
  -F 'message=你好，请介绍一下你能做什么' \
  -F 'session_id=chat_01' \
  -F 'stream=true'
```

非流式：

```bash
curl -sS -X POST 'http://localhost:7777/agents/assistant/runs' \
  -H 'Authorization: Bearer YOUR_JWT' \
  -F 'message=返回一段简短摘要' \
  -F 'session_id=chat_01' \
  -F 'stream=false'
```

多用户生产服务中：

- `user_id` 应由 JWT subject 和 AgentOS 用户隔离机制确定；
- 不信任客户端自行填写的 user ID；
- 客户端负责生成或保存 thread/session ID；
- session ID 不是密钥，权限仍由 JWT 与服务端归属校验决定。

Team 与 Workflow 有对应的 run 路由。最终以运行实例的 `/openapi.json` 为准，客户端 SDK 应从当前 OpenAPI 生成或至少用契约测试锁定。

## 5. Streaming 与事件处理

`stream=true` 时返回事件流。客户端不要把每个 chunk 都当最终文本；应按事件类型处理：

```text
run started
model response delta
reasoning/tool-call events
tool result
HITL requirement
run completed / run error / run cancelled
```

客户端建议维护：

```python
class RunViewState:
    run_id: str | None
    status: str
    text: str
    tool_calls: list
    requirements: list
    error: dict | None
```

实现原则：

1. 保存服务端返回的 `run_id`；
2. 文本 delta 只用于 UI 增量展示；
3. 以终态事件决定成功、失败、暂停或取消；
4. 网络断开不等于服务端 run 失败；
5. 需要重连时使用 AgentOS 支持的 event stream/reconnect 机制，而不是重复提交写请求；
6. UI 必须能显示工具等待、审批等待和错误，不能永远停在“思考中”。

## 6. Background run 与 Queue

长任务可以由 API 接受后在后台执行。使用前明确：

- 请求返回的是接受状态还是最终结果；
- 如何用 run ID 查询状态；
- 是否支持 cancel；
- 应用重启后是否恢复；
- 重复提交如何去重；
- 事件流由单实例内存还是跨实例后端承载。

生产建议：

```text
Client
  ↓ submit + Idempotency-Key
AgentOS API
  ↓ persist run
Durable Queue
  ↓ lease
Worker
  ↓ checkpoints/events
PostgreSQL + Event Stream
```

禁止用无限 `asyncio.create_task()` 代替有界队列。写入类任务必须有业务幂等键。

## 7. Custom FastAPI 路由

可将现有 FastAPI 作为 `base_app`：

```python
from fastapi import FastAPI, Header, HTTPException
from agno.os import AgentOS

base_app = FastAPI()

@base_app.post("/webhooks/provider")
async def provider_webhook(
    x_signature: str = Header(...),
) -> dict[str, bool]:
    if not verify_signature(x_signature):
        raise HTTPException(status_code=401, detail="invalid signature")
    return {"accepted": True}

agent_os = AgentOS(
    base_app=base_app,
    on_route_conflict="error",
    agents=[assistant],
    db=db,
)
app = agent_os.get_app()
```

不要让 webhook、上传、支付回调等路由绕过自身的签名、重放和租户校验。

## 8. CORS

```python
agent_os = AgentOS(
    cors_allowed_origins=[
        "https://app.example.com",
        "https://admin.example.com",
    ],
    ...,
)
```

生产中不要使用 `*` 搭配凭据。CORS 只限制浏览器跨域，不是鉴权；curl、恶意服务端和本地程序不受其保护。

## 9. AgentOS MCP

当前推荐参数名是 `mcp=`；`mcp_server=` 是兼容旧代码的别名，不应在新模板里使用。

### 默认 MCP surface

```python
from agno.os import AgentOS

agent_os = AgentOS(
    agents=[assistant],
    db=db,
    mcp=True,
)
```

默认挂载在：

```text
/mcp
```

安装：

```bash
uv add 'agno[os,mcp]'
```

### 收窄 MCP 工具面

```python
from agno.os import AgentOS, MCPConfig

mcp_config = MCPConfig(
    default_tools=False,
    tools=[
        assistant.as_tool(
            name="ask_support_assistant",
            description="Ask the support assistant a product question",
        ),
    ],
    result_mode="trimmed",
    allowed_hosts=["agent.example.com"],
)

agent_os = AgentOS(
    agents=[assistant],
    db=db,
    mcp=mcp_config,
)
```

MCP 是发布给另一个模型的工具协议，必须把工具名称、描述和权限面当成公开 API 审查。

### MCP 的关键安全差异

直接发布 custom callable/tool 时，调用由 MCP server 直接执行。带 `requires_confirmation`、`requires_user_input` 或 external execution 的 Agno 工具不能被安全地当作普通 direct MCP tool 发布；当前实现会拒绝这类发布，避免绕过审批。

因此：

- 需要 Agent loop + HITL 的动作，发布 Agent/Team/Workflow 为 MCP tool；
- 只把真正可直接执行、无人工审批语义的窄工具作为 custom MCP tool；
- 使用 `allowed_hosts` 防 DNS rebinding；
- 匿名 MCP 必须明确拒绝或仅限本机开发；
- OAuth/JWT/PAT 与 REST 采用一致身份策略。

## 10. Interfaces 的选择

### REST/SSE

适合自有 App、Web、后端服务；契约最可控，通常是默认选择。

### AG-UI

适合支持 Agent 事件、工具状态、共享 UI state 的前端协议。必须测试远端 Agent/Team、错误终态与重连。

### A2A

适合 Agent 与 Agent 平台之间发现和调用。它不自动解决业务信任，仍需鉴权、配额、超时和输入限制。

### Slack/Telegram/WhatsApp/Discord

适合渠道接入。渠道用户 ID 应先映射为内部稳定 user ID，避免一个用户在不同渠道形成互不关联或错误合并的记忆。

### MCP

适合把整个 Agent 平台暴露给 Claude、ChatGPT、IDE Agent 或其他 MCP 客户端。它不是移动 App 的通用聊天传输层。

## 11. Agent Factory 与动态组件

AgentOS 可注册 factory，用请求输入构建差异化组件。仅在以下情况使用：

- Persona 或工具集合必须按租户动态选择；
- 配置来自数据库且数量很大；
- 静态 roster 不现实。

仍应缓存共享资源：模型 client、DB、HTTP client、Knowledge handle、toolkit。不要把 factory 写成“每个 run 重建所有连接”。

Factory 的输入必须有 schema，并且任何 tenant/persona ID 都要经过服务端归属校验。MCP 对带必填 factory input 的组件可能无法像 REST 一样直接调用，发布前做真实客户端测试。

## 12. Scheduler

```python
agent_os = AgentOS(
    db=db,
    agents=[assistant],
    scheduler=True,
    scheduler_base_url="http://agentos:7777",
    internal_service_token=os.environ["AGENTOS_INTERNAL_SERVICE_TOKEN"],
)
```

调度器要求正确的内部回调地址和 token。多副本部署需要确保不会每个副本都重复触发同一 Schedule；使用 AgentOS 当前推荐的 poller/锁机制并做重复触发测试。

## 13. Control Plane / AgentOS UI

AgentOS UI 用于查看平台配置、Sessions、Runs、Traces、Evals 等。它是管理和观测层，不应成为业务数据库的唯一管理界面。

连接外部 Control Plane 前审查：

- 哪些 metadata/traces 会离开你的网络；
- 是否包含 prompt、工具参数、用户输入或 PII；
- 管理员身份与访问日志；
- 数据保留、删除和地区要求；
- 生产与测试平台是否隔离。

## 14. API 契约测试

每次升级 Agno 至少固定这些测试：

```text
[ ] GET /health = 200
[ ] GET /config 中存在预期 agent/team/workflow IDs
[ ] OpenAPI 路径和参数未发生非预期变化
[ ] 非流式 run 返回终态与 content
[ ] 流式 run 以 completed/error/cancelled/paused 终止
[ ] 同 session 续聊成功
[ ] 不同 session 历史隔离
[ ] 不同 JWT 用户无法互读 session/run/memory
[ ] 写工具暂停并可 continue/cancel
[ ] 客户端断开不会重复副作用
[ ] MCP tools/list 只暴露批准的工具
[ ] CORS、Host、JWT、scope 的失败状态符合预期
```
