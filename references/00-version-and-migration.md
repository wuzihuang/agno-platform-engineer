# 版本管理与迁移

## 1. 先确认你面对的是哪一代 Agno

Agno 的教程跨越 Phidata、Agno v1、v2、v3，类名和持久化模型发生过大变化。任何实现前先执行：

```bash
python - <<'PY'
from importlib.metadata import PackageNotFoundError, version

try:
    print(version("agno"))
except PackageNotFoundError:
    print("agno is not installed")
PY
```

然后检查依赖来源：

```bash
grep -RInE '(^|["'"' ])(agno|phidata|phi)([<=>~! ]|$)' \
  pyproject.toml requirements*.txt uv.lock poetry.lock pdm.lock 2>/dev/null || true
```

本 Skill 的研究基线是 2026-09-03 的 Agno `main`：

```text
commit: d829138ae9f28a0dd6967fdfae3c74de11501496
pyproject version: 3.0.5
Python: >=3.9,<4
```

项目安装版本优先于该基线。API 有疑问时查询 `https://docs.agno.com/mcp`，不要从旧博客猜。

## 2. 推荐安装方式

### 最小 SDK

```bash
uv init --python 3.12
uv add agno
```

### AgentOS + OpenAI + PostgreSQL

```bash
uv add 'agno[os,openai,postgres]'
```

### AgentOS + MCP + PostgreSQL

```bash
uv add 'agno[os,mcp,postgres]'
```

### vLLM 客户端

Agno 的 `VLLM` adapter 使用 OpenAI-compatible 服务。客户端项目通常只需要：

```bash
uv add agno openai
```

在推理服务器环境才安装 vLLM 本体：

```bash
uv add vllm
```

### Knowledge 常见 extras

按数据源和向量库组合安装，例如：

```bash
uv add 'agno[pdf,website,pgvector,postgres]'
```

不要为了省事安装所有可选依赖；它会扩大镜像、冲突和供应链风险。

## 3. 旧 API 到当前 API 的核心映射

| 旧写法/概念 | 当前方向 |
|---|---|
| `from phi...` | `from agno...` |
| `storage=` | `db=` |
| `memory=AgentMemory(...)` | `db=` + `update_memory_on_run=True` 或 `enable_agentic_memory=True`，必要时传 `MemoryManager` |
| `PostgresStorage` | `PostgresDb` |
| `SqliteStorage` | `SqliteDb` |
| `MySQLStorage` | `MySQLDb` |
| `RedisStorage` | `RedisDb` |
| `MongoDbStorage` | `MongoDb` |
| `AgentMemory` / `TeamMemory` | 已移除；使用统一 DB 和 MemoryManager |
| `AgentKnowledge`、`PDFUrlKnowledgeBase` 等 | 单一 `Knowledge` + `insert/ainsert` + reader/chunker/vector DB |
| `knowledge_base=` | `knowledge=` |
| `Playground` / `FastAPIApp` | `AgentOS` |
| `RunResponse` | `RunOutput` |
| `TeamRunResponse` | `TeamRunOutput` |
| `WorkflowRunResponse` | `WorkflowRunOutput` |
| `agent_id=` | `id=` |
| `workflow_id=` | `id=` |
| `add_history_to_messages` | `add_history_to_context` |
| `num_history_responses` | `num_history_runs` |
| `enable_user_memories` | v3：`update_memory_on_run` |
| `search_session_history` | v3：`search_past_sessions` |
| `num_history_sessions` | v3：`num_past_sessions_to_search` |
| `num_past_session_runs` | v3：`num_past_session_runs_in_search` |
| `reasoning=True` | 显式传 `reasoning_model=` |
| Workflow 位置参数 | v3 构造器关键字参数，例如 `Workflow(name=..., steps=...)` |
| Workflow flat HITL kwargs | v3 使用 `HumanReview(...)` |
| `continue_run(updated_tools=...)` | v3 使用 `requirements=run.requirements` |
| JWT `secret_key=` | v3 使用 `verification_keys=[...]` |

发现旧 API 时先做迁移设计，不要一边保留旧类一边局部换新类。

## 4. v2 → v3 数据库迁移

v3 的关键变化包括：

1. Run 从 Session 行里的 JSON blob 拆到独立 runs 表；
2. 多张 SQL 表增加 `user_id`，用于用户隔离；
3. 部分向量库需要独立迁移以支持 user-scoped Knowledge。

### 安全顺序

1. 冻结写流量或至少确保可回滚；
2. 备份数据库；
3. 在 staging 运行迁移；
4. 验证 sessions、runs、memory、knowledge、evals；
5. 部署兼容读取的新代码；
6. 观察稳定后再清理旧 runs 字段；
7. 破坏性 cleanup 前再次备份。

### 官方迁移调用形态

```python
import asyncio

from agno.db.migrations.manager import MigrationManager
from agno.db.postgres import PostgresDb

DB_URL = "postgresql+psycopg://user:password@localhost:5432/app"
db = PostgresDb(db_url=DB_URL)

# 非破坏且可重复执行。
asyncio.run(MigrationManager(db).up())

# 必须先验证 run 已迁移。
runs = db.get_runs(limit=5)
assert runs, "No migrated runs found; do not clean the legacy column"

# 只有完成完整验证后才执行。
db.cleanup_legacy_runs_column(force=True)
```

异步 DB adapter 的 `get_runs` 和 cleanup 方法需要 `await`。Mongo/Redis/Valkey/Firestore 等非 SQL adapter 的清理方法名通常是 `cleanup_legacy_runs_field`，仍应按当前文档核验。

### 向量数据库迁移

SQL/schema-based vector store 的旧集合可能缺少 `user_id`。v3 对 user-scoped 搜索可能直接抛错，这是为了避免悄悄返回错误结果。迁移应用 DB 不等于迁移向量库；根据当前仓库 `libs/agno/migrations/v2_to_v3/` 的脚本选择：

- `migrate_sql_vectordbs.py`
- `migrate_field_vectordbs.py`
- `migrate_sentinel_vectordbs.py`

Schemaless store 的旧文档可能继续作为 shared knowledge 可见。上线多租户前必须决定：共享、重建、按用户回填，不能默认其已隔离。

## 5. Workflow v3 HITL 迁移

旧：

```python
Step(
    name="deploy",
    executor=deploy,
    requires_confirmation=True,
    confirmation_message="Deploy?",
)
```

新：

```python
from agno.workflow.step import Step
from agno.workflow.types import HumanReview

step = Step(
    name="deploy",
    executor=deploy,
    human_review=HumanReview(
        requires_confirmation=True,
        confirmation_message="Deploy?",
    ),
)
```

`hitl_max_retries` 改为 `HumanReview(max_retries=...)`，`hitl_timeout` 改为 `HumanReview(timeout=...)`。

## 6. v3 后台任务与队列

v3 对单副本后台 run 有默认并发上限。大规模任务不要自己无限 `asyncio.create_task()`：

- 使用 AgentOS Queue 配置；
- 需要崩溃恢复时启用 durable queue；
- 为提交请求提供 `Idempotency-Key`；
- Redis 只做事件流和跨副本协调，不应成为 run 的唯一事实源；
- DB 是持久化真相。

## 7. 迁移验收

迁移后至少验证：

```text
[ ] 旧 Session 数量与新系统可读数量一致
[ ] 随机抽样 Session 的 run 顺序、输入、输出一致
[ ] 新 run 写入独立 runs 表
[ ] Memory 能按 user_id 读取且无跨用户结果
[ ] Knowledge 在 shared/user-scoped 模式下符合设计
[ ] Evals、schedules、metrics 仍可读取
[ ] HITL paused run 能 continue
[ ] API 与 UI 能读取历史 run
[ ] 旧代码扫描无 phi.*、storage=、AgentMemory 等残留
[ ] 备份和回滚演练成功
```
