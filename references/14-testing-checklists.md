# 测试、评审与交付验收清单

## 1. 测试金字塔

```text
Many: unit tests
Some: integration/contract tests
Fewer: real-model evals
Few: end-to-end/load/chaos simulations
Continuous: production monitoring
```

模型非确定性不意味着“不需要单元测试”。权限、schema、工具、幂等、状态转换都可以确定性测试。

## 2. 基础项目检查

```bash
python -m compileall -q src tests
pytest -q
ruff check .
ruff format --check .
python scripts/inspect_agno_project.py . --strict
```

依赖与安全：

```bash
uv lock --check
# 按团队工具：pip-audit / osv-scanner / trivy / syft 等
```

## 3. Agent 单元测试

```text
[ ] stable id/name/model config
[ ] instructions 不含 secret
[ ] output_schema 可构造并有边界
[ ] tools 只含批准集合
[ ] tool-call limit/timeout 配置
[ ] history window 有上限
[ ] automatic vs agentic memory 只选一种
[ ] Agent 不在 loop/handler 中反复创建
```

## 4. Tool 单元测试

每个工具：

```text
[ ] 参数类型、enum、范围
[ ] docstring 描述行为和限制
[ ] identity 来自 RunContext，不可 spoof
[ ] resource ownership
[ ] timeout
[ ] external error mapping
[ ] output trimming/redaction
[ ] read/write 分离
[ ] write idempotency
[ ] confirmation for side effects
[ ] no secret in errors/logs
```

典型 pytest：

```python
import pytest


def test_get_order_rejects_other_user(fake_context, repo):
    fake_context.user_id = "user-a"
    repo.seed_order(id="order-b", user_id="user-b")

    with pytest.raises(NotFoundError):
        get_order(fake_context, "order-b")
```

## 5. Schema 测试

```text
[ ] happy path
[ ] missing required field
[ ] invalid enum
[ ] max/min boundaries
[ ] null behavior
[ ] cross-field business validation
[ ] serialization/deserialization
[ ] backward compatibility
```

## 6. Session 测试

```text
[ ] first run creates session
[ ] same session continues history
[ ] new session does not inherit chat history
[ ] same user memory can cross session if designed
[ ] different user cannot access session
[ ] session state persists
[ ] concurrent turns have deterministic order/conflict behavior
[ ] cancel and reconnect
[ ] delete/export
```

## 7. Memory 测试

```text
[ ] explicit stable fact stored
[ ] temporary fact not stored
[ ] duplicate merged
[ ] changed preference updated
[ ] explicit forget deletes
[ ] new session recalls
[ ] wrong Persona scope does not recall
[ ] wrong user never recalls
[ ] sensitive data blocked/redacted
[ ] memory count/latency/token within budget
```

## 8. Knowledge/RAG 测试

### Ingestion

```text
[ ] supported type
[ ] malformed/oversized file
[ ] duplicate hash
[ ] update/new version
[ ] delete source removes vectors
[ ] partial failure and retry
[ ] metadata/permissions
```

### Retrieval

```text
[ ] known query hit@k
[ ] exact identifier/BM25
[ ] semantic paraphrase
[ ] no-answer query
[ ] tenant/user filter
[ ] stale source handling
[ ] conflicting sources
[ ] injection document
```

### Answer

```text
[ ] grounded facts
[ ] correct source IDs
[ ] abstains without evidence
[ ] no cross-tenant citations
[ ] no document instruction overrides policy
```

## 9. Team 测试

```text
[ ] leader selects expected member
[ ] forbidden member not selected
[ ] max delegation respected
[ ] member output schema valid
[ ] member failure behavior
[ ] disagreements surfaced
[ ] final answer uses evidence
[ ] no shared mutable user state
[ ] cost/latency vs single-agent baseline
[ ] quality improvement statistically meaningful
```

## 10. Workflow 测试

```text
[ ] every branch
[ ] parallel join
[ ] child failure
[ ] retries by error type
[ ] loop goal reached
[ ] loop max reached
[ ] router invalid result
[ ] HITL approve/reject/timeout
[ ] cancel
[ ] restart/resume
[ ] old run with new deployment compatibility
[ ] side-effect exactly-once effect through idempotency
[ ] audit contains step inputs/outputs/status
```

## 11. AgentOS API contract

```text
[ ] /health
[ ] /config
[ ] /openapi.json snapshot or semantic diff
[ ] agent/team/workflow run endpoints
[ ] multipart text/file input
[ ] non-stream response
[ ] SSE event order and terminal state
[ ] error event
[ ] cancel/continue/resume
[ ] session/run list/get
[ ] pagination
[ ] max upload and malformed data
[ ] CORS preflight
[ ] request IDs
```

## 12. MCP contract

```text
[ ] tools/list only approved tools
[ ] default_tools/include/exclude behavior
[ ] stable tool names/descriptions/schema
[ ] identity injection cannot be spoofed
[ ] JWT/OAuth/PAT
[ ] Host/Origin rejection
[ ] component scope
[ ] result_mode trimmed/full as intended
[ ] paused run can continue/cancel when exposed
[ ] confirmation-required direct tool is refused
[ ] no zero-tool accidental server
```

## 13. Security matrix

```text
[ ] missing token
[ ] bad signature
[ ] expired token
[ ] wrong audience/issuer/algorithm
[ ] missing scope
[ ] admin escalation
[ ] IDOR for session/run/order/file
[ ] cross-user memory/knowledge/trace
[ ] user_id/tenant_id spoof
[ ] prompt injection through user/tool/doc/MCP
[ ] secret exfiltration
[ ] path traversal/upload abuse
[ ] rate limit bypass
[ ] replay/idempotency
[ ] audit log completeness
[ ] data deletion/export
```

## 14. Concurrency tests

至少模拟：

```text
same user + same session
same user + different sessions
different users + same Agent
different tenants
concurrent memory writes
concurrent state writes
concurrent confirmed tool execution
multiple AgentOS replicas
queue retry/lease expiry
scheduler duplicate pickup
```

检查：

- 顺序；
- 数据隔离；
- DB locks；
- connection pools；
- duplicate side effects；
- shared toolkit state；
- event delivery；
- cancellation。

## 15. Load test 场景

分开压测：

1. 空 AgentOS endpoint baseline；
2. mock model；
3. real model no tools；
4. real model + internal read tool；
5. streaming；
6. Knowledge；
7. Memory update；
8. Team/Workflow；
9. background queue。

指标：

```text
RPS/concurrency
p50/p95/p99 TTFT
p50/p95/p99 total latency
error/timeout/cancel
DB pool
CPU/memory
model 429
queue depth
cost/success
```

## 16. Fault injection

```text
model timeout/429/5xx
model returns malformed structured output
tool timeout/partial success
DB unavailable/slow
Redis/event stream unavailable
vector DB unavailable
object storage failure
client disconnect
worker crash after side effect before ack
HITL timeout
process restart during workflow
```

对每种故障定义：重试、降级、暂停、失败、补偿和用户提示。

## 17. Migration tests

```text
[ ] backup can restore
[ ] migration up is idempotent
[ ] sessions count/sample
[ ] runs extracted correctly
[ ] memory user_id
[ ] traces/evals/schedules
[ ] vector DB migration
[ ] old/new app compatibility window
[ ] cleanup only after validation
[ ] rollback or forward-fix practiced
```

## 18. Model upgrade checklist

```text
[ ] exact model ID/provider/region
[ ] context/output limits
[ ] tool calling
[ ] structured output
[ ] streaming
[ ] multimodal
[ ] safety behavior
[ ] latency/cost
[ ] fallback compatibility
[ ] eval comparison on same dataset
[ ] canary/shadow
[ ] rollback flag
```

## 19. Prompt/Persona upgrade checklist

```text
[ ] versioned artifact
[ ] diff reviewed
[ ] no secret/internal endpoint
[ ] conflicts with platform policy checked
[ ] persona consistency eval
[ ] memory extraction impact
[ ] tool-call impact
[ ] token change
[ ] adversarial tests
[ ] canary and rollback
```

## 20. Code review checklist

### Architecture

```text
[ ] simplest valid primitive
[ ] deterministic code used where possible
[ ] state ownership explicit
[ ] no per-request Agent construction
[ ] no hidden global mutable user state
```

### Security

```text
[ ] identity trusted
[ ] user isolation
[ ] least-privilege tools
[ ] side effects confirmed/idempotent
[ ] secrets and PII handling
```

### Reliability

```text
[ ] timeout/retry/error taxonomy
[ ] terminal stream states
[ ] resume/cancel
[ ] fallback behavior
[ ] observability
```

### Quality

```text
[ ] output contract
[ ] eval cases
[ ] no hallucinated business fact path
[ ] RAG citations/abstention
[ ] cost/latency budget
```

## 21. Release gate

建议硬门槛：

```text
0 cross-user leakage
0 unconfirmed high-impact action
100% schema validation in deterministic fixtures
all security/auth contract tests pass
no unresolved high-severity inspector findings
no migration data-loss discrepancy
quality not below approved threshold
p95 and cost within budget
rollback tested
```

## 22. 交付报告模板

```markdown
# Agno 实施报告

## Baseline
- Agno/Python versions:
- Commit/image:
- Model/provider:
- DB/vector/event backends:

## Architecture
- Primitive:
- AgentOS interfaces:
- State/memory/knowledge boundaries:
- Auth/isolation:

## Changes
- Files:
- APIs:
- Migrations:

## Validation
- Unit/integration/eval:
- Load/security:
- Results and thresholds:

## Operations
- Startup/health:
- Metrics/alerts:
- Backup/rollback:

## Remaining Risks
- Unverified:
- Accepted tradeoffs:
- Owner/date:
```

## 23. Definition of Done

```text
[ ] code runs in clean environment
[ ] version-sensitive API verified
[ ] user/session semantics documented
[ ] production DB and migrations ready
[ ] auth and isolation tested
[ ] tools safe and idempotent
[ ] traces usable
[ ] eval suite repeatable
[ ] load/concurrency behavior known
[ ] deploy and rollback commands documented
[ ] data export/delete path documented
[ ] no known critical issue hidden in “future work”
```
