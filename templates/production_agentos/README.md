# Agno Production AgentOS Starter

A deliberately small Agno 3.x service that demonstrates the boundaries a real multi-user deployment needs:

- one reusable `Agent` object;
- `PostgresDb` persistence;
- environment-selectable OpenAI, vLLM, or another OpenAI-compatible model;
- Pydantic output contract;
- Session history and optional automatic user memory;
- a read tool plus a confirmation-gated handoff example;
- `AgentOS` REST/SSE, optional MCP, tracing, CORS, JWT, and `user_isolation`;
- Docker Compose and smoke tests.

The handoff tool stores a demo request in Session State. Replace it with an idempotent, tenant-aware business service before production.

## 1. Local setup

```bash
cp .env.example .env
uv sync --extra dev
```

This starter does not load `.env` automatically. Export it in your shell or use a process manager:

```bash
set -a
. ./.env
set +a
```

Start PostgreSQL:

```bash
docker compose up -d postgres
```

Run:

```bash
uv run agno-app
```

Inspect:

```text
http://localhost:7777/health
http://localhost:7777/config
http://localhost:7777/docs
```

## 2. Call the Agent

Non-streaming:

```bash
curl -sS -X POST http://localhost:7777/agents/support-assistant-v1/runs \
  -F 'message=Explain what you can help with' \
  -F 'session_id=session_demo_001' \
  -F 'stream=false'
```

Streaming:

```bash
curl -N -X POST http://localhost:7777/agents/support-assistant-v1/runs \
  -F 'message=Help me troubleshoot a login issue' \
  -F 'session_id=session_demo_001' \
  -F 'stream=true'
```

The authoritative request contract is the running service's `/openapi.json`.

## 3. OpenAI

```bash
export MODEL_PROVIDER=openai
export MODEL_ID=gpt-5.5
export OPENAI_API_KEY=...
```

`MODEL_API_KEY` can also be used by the template's model factory.

## 4. vLLM

Start an OpenAI-compatible vLLM server separately, then:

```bash
export MODEL_PROVIDER=vllm
export MODEL_ID='Qwen/Qwen2.5-7B-Instruct'
export MODEL_BASE_URL='http://localhost:8000/v1/'
export MODEL_API_KEY='local-token'
```

Alternatively use `VLLM_BASE_URL` and `VLLM_API_KEY` when `MODEL_BASE_URL`/`MODEL_API_KEY` are not explicitly passed by your configuration. The served model name must match `MODEL_ID`.

Tool calling requires a model, chat template, and vLLM tool-call parser that agree. Test raw OpenAI-compatible tool calls before enabling any write tool.

## 5. Production authentication

The template refuses to start with `APP_ENV=production` unless authorization is enabled.

Set:

```bash
export APP_ENV=production
export AUTHORIZATION_ENABLED=true
export JWT_ALGORITHM=RS256
export JWT_AUDIENCE=agent-api
export JWT_VERIFICATION_KEY='-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----'
export CORS_ALLOWED_ORIGINS='https://app.example.com,https://admin.example.com'
```

`app.py` constructs:

```python
AuthorizationConfig(
    verification_keys=[...],
    algorithm="RS256",
    verify_audience=True,
    audience="agent-api",
    admin_scope="agent_os:admin",
    user_isolation=True,
)
```

After enabling auth, calls need a bearer token with the relevant AgentOS component scope. Use your actual identity provider and current Agno scope documentation rather than copying a development token into production.

Never trust a mobile or browser client to select its own effective `user_id`. With user isolation enabled, the verified JWT subject is the platform identity boundary. Custom business tools must still enforce their own tenant and resource ownership.

## 6. Memory

Memory is off by default:

```bash
MEMORY_ENABLED=false
```

After authenticated identity, privacy, deletion, and eval semantics are defined:

```bash
MEMORY_ENABLED=true
```

The Agent then uses `update_memory_on_run=True`. Do not additionally turn on Agentic Memory without deliberately replacing this mode. Build tests for should-store, should-not-store, update, delete, cross-session recall, and zero cross-user leakage.

## 7. MCP

Enable the default AgentOS MCP operator surface:

```bash
MCP_ENABLED=true
MCP_ALLOWED_HOSTS=agent.example.com
```

The service mounts MCP at `/mcp`. New code uses `AgentOS(mcp=...)`; `mcp_server=` is a deprecated compatibility alias.

Before publishing MCP externally:

- authenticate it;
- restrict hosts/origins;
- reduce the tools surface with `MCPConfig`;
- verify per-component scopes;
- do not directly publish confirmation-required custom tools;
- run a real client `tools/list` and invocation test.

## 8. Replace the demo tools

`get_runtime_context` is read-only. `request_human_handoff` demonstrates `RunContext`, Session State, idempotency, and `@tool(requires_confirmation=True)` but does not create a real support ticket.

A production replacement should:

```text
read trusted run_context.user_id
validate user/tenant/resource ownership
use a business idempotency key
write through a durable service/database transaction
return a small, redacted result
record audit metadata
verify the external result after uncertain timeouts
```

Do not keep business queues in Session State.

## 9. Tests

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
python -m compileall -q src tests
```

The supplied smoke test builds the AgentOS app without opening a real database connection or calling a model. Add integration tests using an isolated PostgreSQL database and model/tool mocks.

## 10. Docker Compose

```bash
export OPENAI_API_KEY=...
docker compose up --build
```

The compose file is for development. Before production, replace credentials, enable JWT, use managed PostgreSQL or durable volumes/backups, configure TLS, run as a hardened workload, and add readiness/metrics/alerts.

## 11. Recommended next files

```text
src/agno_app/
├── repositories/          # tenant-aware business persistence
├── security/              # claims, policy, scope helpers
├── knowledge/             # ingestion and retrieval
├── workflows/             # deterministic long tasks
├── evals/                 # quality/reliability datasets
└── observability/         # metrics and redaction
```

Keep the Agent configuration reusable and immutable. Request handlers should resolve identity, session, persona/dependencies, then invoke the shared Agent/Team/Workflow.

## 12. Release gate

```text
[ ] PostgreSQL migrations and backup/restore tested
[ ] JWT signature/algorithm/expiry/audience verified
[ ] AuthorizationConfig(user_isolation=True)
[ ] custom tools enforce tenant ownership
[ ] write tools are confirmed and idempotent
[ ] no per-request Agent/DB/toolkit construction
[ ] SSE terminal and reconnect behavior tested
[ ] cross-user session/memory/knowledge tests pass
[ ] tracing, metrics, alerts, and redaction configured
[ ] model/tool/RAG/memory eval thresholds pass
[ ] load test and rollback completed
```
