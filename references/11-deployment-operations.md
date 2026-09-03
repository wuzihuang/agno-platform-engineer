# 部署、数据库、并发、队列与运行维护

## 1. 生产拓扑

推荐最小拓扑：

```text
Client / Backend
      ↓ HTTPS
Load Balancer / API Gateway
      ↓
AgentOS replicas
  ├─ shared PostgreSQL
  ├─ optional Redis/event stream/queue
  ├─ object storage
  ├─ vector database
  ├─ model providers or vLLM
  └─ OpenTelemetry collector
```

AgentOS 容器应尽量无状态；Session、Run、Memory、Knowledge metadata、queue state 不放本地磁盘。

## 2. 开发与生产数据库

### 开发

```python
from agno.db.sqlite import SqliteDb

db = SqliteDb(db_file="tmp/dev.db")
```

### 生产

```python
from agno.db.postgres import PostgresDb

db = PostgresDb(
    id="agent-platform-db",
    db_url=os.environ["DATABASE_URL"],
)
```

安装：

```bash
uv add 'agno[postgres]'
```

多副本、多进程和高并发不要使用共享单文件 SQLite。

## 3. PostgreSQL 连接

生产检查：

- 使用连接池；
- 设置 pool size 与 overflow；
- DB 连接数预算覆盖 web replicas、workers、migrations；
- TCP/statement/idle timeout；
- TLS；
- 读写账号最小权限；
- 密钥轮换；
- 慢查询和锁监控；
- backup/PITR；
- schema migration 单独执行。

不要让每个 Agent 实例新建一个独立连接池。模块级复用 `PostgresDb`。

## 4. 进程模型

容器里通常采用：

```text
1 container = 1 or a small fixed number of ASGI workers
```

LLM 请求主要是 I/O；优先 async 和适度并发，而不是大量 Python workers。每加一个 worker 都会复制：

- Agent/Team/Workflow objects；
- HTTP client/pools；
- model metadata；
- toolkit clients；
- in-memory caches。

先压测，再决定 worker 和 replica 数。

## 5. Agent 生命周期

正确：

```python
db = build_db()
model = build_model()
assistant = build_agent(db=db, model=model)
agent_os = build_agent_os(...)
```

全部模块级或应用 lifespan 构造一次。

错误：

```python
@app.post("/chat")
async def chat(...):
    agent = Agent(...)
    return await agent.arun(...)
```

后者会重复初始化工具、连接、MCP session 和配置，且难以追踪稳定 component ID。

## 6. Async

服务端优先：

```python
result = await assistant.arun(
    message,
    user_id=user_id,
    session_id=session_id,
)
```

自定义工具也提供 async 实现，避免在 event loop 中运行阻塞网络/磁盘。没有 async SDK 时：

- 使用受限 thread pool；
- 设置 timeout；
- 限制并发；
- 监控 thread saturation。

## 7. Concurrency budget

对每种资源设独立 semaphore/限额：

```text
HTTP requests
active agent runs
model calls by provider/model
embedding jobs
tool calls by provider
GPU generation jobs
background workers
per-user runs
```

例如同一用户只允许 1–2 个活跃聊天 run，可避免乱序 Memory/Session 更新；图片和长任务进入独立队列。

## 8. Horizontal scaling

水平扩展前确认：

- 所有长期状态在共享 DB；
- event stream 支持跨实例；
- background queue 可 lease/ack；
- scheduler 不重复触发；
- HITL resume 能在另一个 replica 完成；
- session affinity 不是正确性前提；
- 本地上传先进入 object storage；
- 所有写工具幂等。

如果只有 in-memory event buffer，断线重连或跨 replica 可能无法恢复完整 stream。

## 9. Queue

适合：

- 长研究；
- Knowledge ingestion；
- 批量评测；
- 图像/音频生成；
- 定时主动触达；
- 高峰削峰。

任务记录至少包括：

```text
job_id
idempotency_key
user_id/tenant_id
component_id
input reference
status
attempt
lease owner/expiry
created/started/finished
error category
result/run_id
```

重试策略按错误类别区分：

- timeout/429/temporary 5xx：有限退避；
- validation/permission：不重试；
- uncertain side-effect：先查询外部结果再决定；
- poison task：进入 dead-letter queue。

## 10. Event Stream

Event stream 与事实持久层职责不同：

- PostgreSQL：Run 的事实状态；
- Redis/stream backend：实时传递和短期重连；
- Object storage：大文件/媒体；
- Metrics backend：聚合时间序列。

Redis 不应成为唯一 Run 真相；丢失 Redis 数据后应仍能从 DB 查询最终状态。

## 11. Scheduler

定时任务设计：

- 使用稳定 schedule ID；
- timezone 明确；
- misfire/catch-up 策略；
- 防重复执行；
- 每次产生 run/job ID；
- 用户取消订阅后立即生效；
- 主动消息有频控与 quiet hours；
- scheduler 内部 token 可轮换。

多副本中要验证只有一个逻辑执行者领取同一次触发。

## 12. Dockerfile 原则

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

USER 10001
EXPOSE 7777
CMD ["python", "-m", "agno_app.app"]
```

生产强化：

- lockfile/hash；
- multi-stage；
- 非 root；
- read-only root FS；
- SBOM/镜像扫描；
- 不把 `.env` 和 credentials COPY 进 image；
- 固定基础镜像 digest；
- healthcheck；
- 资源 request/limit。

## 13. Environment 配置

必需配置应 fail fast：

```python
DATABASE_URL = require_env("DATABASE_URL")
MODEL_ID = require_env("MODEL_ID")
```

生产安全配置不能用危险默认值：

```python
if environment == "production" and not authorization_enabled:
    raise RuntimeError("Authorization must be enabled in production")
```

建议环境变量：

```text
APP_ENV
DATABASE_URL
MODEL_PROVIDER
MODEL_ID
MODEL_BASE_URL
MODEL_API_KEY
AUTHORIZATION_ENABLED
JWT_VERIFICATION_KEY / JWKS_FILE
JWT_AUDIENCE
CORS_ALLOWED_ORIGINS
TRACING_ENABLED
MCP_ENABLED
AGNO_TELEMETRY
LOG_LEVEL
```

## 14. Health 与 Readiness

`/health` 适合作为进程存活探针。Readiness 还应考虑：

- DB 是否可查询；
- 必需配置是否加载；
- migration 是否完成；
- event/queue backend 是否可用；
- 关键依赖是否降级或熔断。

不要在每次 liveness probe 调用昂贵模型 API。模型 provider 状态使用独立的低频 dependency health/metrics。

## 15. Graceful shutdown

终止时：

1. readiness 先变 false；
2. 停止接受新任务；
3. 给流式请求和当前 runs 合理 drain 时间；
4. queue worker 停止领取新 lease；
5. 未完成任务释放/延长 lease 或持久化 checkpoint；
6. flush telemetry/log；
7. 关闭 DB、HTTP、MCP clients。

Kubernetes `terminationGracePeriodSeconds` 要大于应用 drain 上限。

## 16. Timeout

分层设置：

```text
Load balancer timeout
HTTP request timeout
Agent run timeout
Model call timeout
Tool timeout
DB statement timeout
Queue task timeout
HITL timeout
```

外层 timeout 不能短于内层最大执行时间却不触发 cancel，否则客户端断开后服务器仍继续烧 token。

## 17. Retry 与 fallback

只对可恢复错误重试。模型 fallback 应记录：

- primary error；
- fallback model；
- output quality difference；
- cost；
- structured/tool capability compatibility。

Fallback 不能从支持工具调用的模型切到不支持工具的模型，却仍允许写动作继续。

## 18. Cost control

控制点：

- model routing；
- max tokens；
- history window；
- context compression；
- tool result trimming；
- RAG top-k；
- memory frequency；
- caching；
- Team 成员数；
- loop max iterations；
- per-user quota；
- background priority queue。

核心指标是 `cost / successful task`，而不只是 token 总量。

## 19. vLLM / 自托管模型

拓扑：

```text
AgentOS CPU service
  ↓ OpenAI-compatible HTTP
vLLM GPU service
```

不要把 AgentOS web workers 与重量级 vLLM engine 强行放一个进程。独立扩缩容并监控：

- TTFT；
- inter-token latency；
- queue length；
- KV cache utilization；
- prefill/decode throughput；
- OOM；
- parser/tool-call error；
- context length rejection。

## 20. 数据库迁移

发布流程：

```text
backup
→ migrate in staging
→ backward-compatible schema change
→ deploy code
→ verify
→ later remove legacy fields
```

不要让多个 web replica 启动时并发执行破坏性 migration。AgentOS `auto_provision_dbs` 可建必要表，但版本迁移和业务 schema 仍应走专门 job。

## 21. 备份与恢复

至少覆盖：

- PostgreSQL PITR；
- vector DB snapshot/rebuild source；
- object storage versioning；
- secrets/config backup；
- eval datasets；
- deployment manifests。

演练：

```text
[ ] 从备份恢复到隔离环境
[ ] Sessions/Runs/Memory 可读
[ ] Knowledge vectors 可恢复或重建
[ ] 用户删除 tombstone 不会在恢复后复活
[ ] 恢复后的 service accounts 已轮换
```

## 22. 发布策略

### Rolling

要求 API/DB backward compatible。

### Blue/green

适合重大 Agno/model/schema 升级；切流快，成本更高。

### Canary

按内部用户/tenant/比例放量，比较成功率、延迟、成本和质量。

### Shadow

复制只读流量到新版本，不执行写工具；用于模型或 prompt 对比。

## 23. 回滚

回滚包必须包含：

- 前一镜像 digest；
- DB schema 兼容说明；
- model/prompt/config 版本；
- feature flags；
- queue 中旧任务处理策略；
- migration rollback 或 forward-fix 方案。

模型和 prompt 也是发布物，必须可定位版本。

## 24. 运维 Runbook

常见告警：

```text
error rate high
TTFT/latency high
queue backlog
model 429/5xx
DB pool exhaustion
memory write spike
knowledge empty search spike
tool timeout spike
structured output failures
cross-user security alert
cost anomaly
```

每个告警写：影响、确认命令、临时缓解、根因定位、升级人和回滚条件。

## 25. 上线清单

```text
[ ] 生产 Postgres，不使用本地 SQLite
[ ] JWT + user_isolation
[ ] CORS allowlist
[ ] 非 root image，无内置 secrets
[ ] /health 与 readiness
[ ] tracing + metrics + alerts
[ ] concurrency/rate limit
[ ] tool timeout/idempotency/HITL
[ ] durable state/event/queue 设计
[ ] migrations 与 backup
[ ] load/concurrency/security/eval 通过
[ ] canary 与 rollback 可执行
[ ] AGNO_TELEMETRY 决策明确
```
