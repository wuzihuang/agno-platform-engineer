# 安全、JWT、RBAC 与多租户隔离

## 1. 先建立威胁模型

Agent 平台至少面对五类边界：

```text
Internet client
  ↓ authentication
AgentOS API / MCP / channel interface
  ↓ authorization + user isolation
Agent / Team / Workflow
  ↓ tool policy + HITL
Business services / databases
  ↓ row/resource ownership + transaction
External providers
```

任何一层都不能把下一层当作“已经可信”。Prompt 不能替代权限；CORS 不能替代 JWT；JWT 不能替代业务资源归属；HITL 不能替代幂等和事务。

## 2. 开发模式与生产模式

### 本机演示

可暂时关闭 authorization，但必须绑定 loopback 或受控网络，禁止暴露公网：

```python
AgentOS(
    authorization=False,
    cors_allowed_origins=["http://localhost:3000"],
)
```

### 共享测试环境

至少启用一个强随机 security key 或 JWT。测试 key 不得复用生产 key。

### 生产

使用签名 JWT、过期时间、audience、最小 scopes 与 `user_isolation=True`：

```python
from agno.os import AgentOS
from agno.os.config import AuthorizationConfig

authorization_config = AuthorizationConfig(
    verification_keys=[os.environ["JWT_VERIFICATION_KEY"]],
    algorithm="RS256",
    verify_audience=True,
    audience="agent-api",
    admin_scope="agent_os:admin",
    user_isolation=True,
)

agent_os = AgentOS(
    authorization=True,
    authorization_config=authorization_config,
    db=db,
    agents=[assistant],
)
```

也可以使用当前版本支持的 JWKS file/provider 方式。不要让应用在生产环境因缺少 key 而静默退回无鉴权模式。

## 3. `user_isolation` 为什么必须显式开启

`authorization=True` 负责验证 token 和 scope，但当前 `AuthorizationConfig.user_isolation` 默认是 `False`。关闭时，JWT/RBAC 仍可能生效，但 Session、Memory、Trace 等数据库读取不会自动叠加每用户所有权边界。

生产多用户服务应明确：

```python
AuthorizationConfig(user_isolation=True)
```

开启后，AgentOS 会把 JWT subject 作为可信 `user_id`，并对用户作用域的读写、Session/Run 的取消与恢复执行归属限制。

仍需注意：AgentOS 用户隔离不自动覆盖你自定义业务数据库的所有表。工具查询订单、订阅、照片、设备时必须再次按可信 user/tenant 过滤。

## 4. JWT 基本要求

每个 token 至少验证：

- signature；
- 固定允许的 algorithm；
- `exp`；
- `nbf`/`iat` 的时钟偏差策略；
- `aud`；
- `iss`，若平台有明确 issuer；
- `sub` 非空且稳定；
- scopes/roles。

禁止：

- 接受客户端指定 `alg=none`；
- 同时接受过宽算法集合；
- 把 access token 当永久 token；
- 在 query string 传 token；
- 在日志记录完整 token；
- 用邮箱作为永不变化的唯一 ID；
- 将同一个 `sub` 在不同租户复用且不带 tenant namespace。

推荐内部主体：

```text
subject = tenant_id + ":" + immutable_user_id
```

或在 claims 中分别保留 `tenant_id`，业务工具强制验证。

## 5. Scope 设计

采用最小权限，不给普通客户端管理员 scope。可按当前 AgentOS 的 scope 约定配置，例如：

```text
agents:read
agents:assistant:run
agents:*:run
teams:research-team:run
workflows:publish-flow:run
agent_os:admin
```

设计建议：

- 移动客户端只获得允许运行的 Agent scope；
- 内部 worker 使用 service account；
- 管理 UI 使用单独管理员身份；
- 写工具还应在工具内部检查业务权限；
- 生产与 staging 使用不同 audience/issuer/key。

## 6. Service Accounts

服务间调用使用短期 JWT 或 AgentOS 支持的 service account/PAT。服务账户应：

- 有独立主体；
- 只拥有所需组件 scopes；
- 可轮换、吊销；
- 与人类管理员分离；
- 在审计日志中可识别；
- 不嵌入客户端 App。

不要把 `agno_pat_*` 或任何长期 token 打包进移动端、前端 JS、公开镜像或 Skill 模板。

## 7. 多租户数据模型

建议所有用户级业务记录都包含：

```text
tenant_id
user_id
resource_id
created_at
updated_at
deleted_at / status
```

数据库层可进一步使用：

- PostgreSQL Row Level Security；
- 每租户 schema/database；
- repository 函数强制 tenant 参数；
- composite primary/unique key；
-审计 trigger。

仅在查询字符串中“记得加 user_id”不够稳。

## 8. 自定义工具的身份传递

工具应从可信 `RunContext` 或服务端 dependency 获取身份，而不是把 `user_id` 暴露为模型可自由填写的普通参数：

```python
from agno.run import RunContext


def get_my_orders(run_context: RunContext, limit: int = 20) -> list[dict]:
    user_id = run_context.user_id
    if not user_id:
        raise PermissionError("authenticated user required")
    return order_repository.list_for_user(user_id=user_id, limit=limit)
```

业务仓库函数也要接受 user ID：

```python
def get_order(*, user_id: str, order_id: str) -> Order:
    order = db.fetch_one(
        "SELECT * FROM orders WHERE user_id = :user_id AND id = :id",
        {"user_id": user_id, "id": order_id},
    )
    if order is None:
        raise NotFoundError()
    return order
```

不要先按 `order_id` 查出记录，再仅依赖 Agent prompt 判断是否属于用户。

## 9. Session ID 与对象枚举

Session ID 应使用高熵随机 ID，但“难猜”不是权限。攻击者获得另一个 session ID 后仍必须被 ownership check 拒绝。

错误处理应避免泄露：

- 对不存在和无权访问的资源都返回一致的 404/403 策略；
- 不在错误里输出其他用户的 ID、email、prompt；
- 列表接口始终服务端加 user/tenant filter；
- cancel/continue/resume 同样校验归属。

## 10. 工具权限分层

建议分为：

### Read-only

查询余额、状态、文档。仍可能泄露敏感数据，必须鉴权与最小返回字段。

### Reversible write

改昵称、修改偏好、创建草稿。要求确认、审计和幂等。

### Irreversible/high-impact

支付、删除数据、发送消息、发布内容、部署、签署。要求更强认证、确认、业务风控或人工审批。

### Admin

跨用户查询、导出、封禁、策略修改。不要放进普通 Agent 的工具列表。

## 11. HITL 不是万能安全边界

确认工具只能确认模型准备执行的动作。仍需：

- 展示准确预览；
- 确认动作与执行动作绑定同一参数 hash；
- 审批过期；
- 执行前再次授权；
- 幂等；
- 结果核验；
- 审计。

用户确认“删除文件 A”后，不得允许模型在 continue 时替换为文件 B。

## 12. Prompt Injection 防护

把所有外部文本视为不可信数据：

- Knowledge 文档；
- 网页；
- Email/Slack；
- 工具结果；
- 用户上传文件；
- MCP 返回；
- 另一个 Agent 的输出。

防护层：

1. System policy 明确外部内容不能修改权限；
2. 工具列表最小化；
3. 参数 schema 与 allowlist；
4. 服务端资源归属；
5. 写工具确认；
6. 输出内容与 tool call 分离；
7. 对高风险数据源进行注入检测/标记；
8. 安全 eval。

“忽略上文”过滤器不能解决 Prompt Injection。

## 13. MCP 安全

MCP 可能让外部模型发现和调用工具。至少控制：

- JWT/OAuth/PAT；
- `MCPConfig.authorize`；
- `allowed_hosts`；
- tool publication allowlist；
- per-component scopes；
- rate limits；
- model-facing description 不泄露内部信息；
- 不直接发布绕过 HITL 的副作用工具；
- tool result 截断与敏感字段清理。

本机常驻 MCP server 也要防 DNS rebinding，不要因为监听 localhost 就忽略 Host/Origin 校验。

## 14. Secrets

密钥只从：

- 环境变量；
- Kubernetes Secret；
- Cloud Secret Manager；
- Vault/KMS；
- 短期 workload identity；

读取。

禁止存入：

- Agent instructions；
- Memory；
- Knowledge；
- Session State；
- trace attributes；
- Git；
- Docker image layer；
- 客户端日志。

工具错误应对外返回安全消息，对内用 error ID 关联完整受控日志。

## 15. 日志与 PII

日志分级：

```text
Operational metadata: run_id, component_id, latency, status
Restricted metadata: user_id hash, tool name, error category
Sensitive payload: prompts, tool args/results, files, memory
```

默认不要记录完整敏感 payload。需要排错采样时：

- 有权限开关；
- 脱敏；
- 短保留；
- 加密；
- 访问审计；
- 用户删除时同步处理。

## 16. Rate Limit 与配额

至少按：

- IP；
- user；
- tenant；
- component；
- model/provider；
- tool；

设置限流或配额。限制：

- concurrent runs；
- queued runs；
- tokens/minute；
- tool calls/run；
- uploads/day；
- Knowledge ingestion size；
- memory writes/day；
- write actions/day。

限流结果要可观测，不要只让模型收到含糊的“工具失败”。

## 17. 删除、导出与保留

设计用户删除时明确覆盖：

```text
sessions
runs
memories
learning records
traces
uploaded objects
knowledge contents
vector chunks
cache
generated media
business records subject to legal retention
external memory providers
```

软删除与法定保留必须可解释。备份中的最终删除时间也应定义。

## 18. 并发与共享对象

AgentOS 会为 run 创建运行上下文，但模型 client、DB、Knowledge、Toolkit 或自定义对象可能共享。任何共享可变状态都要：

- 无状态化；
- 使用协程/线程安全连接池；
- 按 session/user key 存进 DB/Redis，而非 Python 全局 dict；
- 有竞争测试；
- 不在共享 Agent 字段写用户数据。

## 19. 安全测试矩阵

```text
[ ] 无 token 访问受保护路径失败
[ ] 错签名、过期、错误 audience、错误 issuer 失败
[ ] 缺 scope 失败
[ ] 普通用户无法使用 admin scope
[ ] user A 无法读/列出/cancel/continue user B 的 session/run
[ ] user A 无法召回 user B memory
[ ] user A 无法检索 user B private knowledge
[ ] 自定义工具无法通过参数 spoof user_id/tenant_id
[ ] 资源 ID 枚举不泄露存在性或内容
[ ] 写工具确认后参数不能被替换
[ ] 重复请求不会重复扣款/发送/删除
[ ] Prompt injection 不能提升权限或调用未授权工具
[ ] MCP tools/list 不暴露未批准组件
[ ] 日志、trace、错误无 token/secret/敏感字段
[ ] 删除/导出覆盖所有存储副本
```
