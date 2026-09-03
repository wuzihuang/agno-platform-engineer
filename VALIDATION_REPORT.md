# Validation report

## Baseline

- Skill: `agno-platform-engineer`
- Skill version: `1.0.0`
- Verified date: `2026-09-03`
- Agno repository baseline: `d829138ae9f28a0dd6967fdfae3c74de11501496`
- Agno package version at that baseline: `3.0.5`

## Checks completed

### 1. Skill structure and frontmatter

Command:

```bash
python scripts/validate_skill.py . --warnings-as-errors
```

Result:

```text
0 errors, 0 warnings
PASS: Skill structure and Python syntax are valid
```

This validates the required `SKILL.md`, YAML frontmatter, skill name/directory match, description limits, local file references, script permissions, and syntax of all Python templates and scripts.

### 2. Production-template architecture scan

Command:

```bash
python scripts/inspect_agno_project.py templates/production_agentos --strict --json
```

Result:

```text
HIGH=0, MEDIUM=0, LOW=0
```

The scanner found a reusable Agent and AgentOS, PostgreSQL, tests, Docker files, tracing, and evals, with no known legacy API, per-request construction, missing isolation, or production-pattern finding.

### 3. Scaffold round-trip

Command:

```bash
python scripts/scaffold_agno_app.py /tmp/agno-scaffold-test --project-name agno-demo
python scripts/inspect_agno_project.py /tmp/agno-scaffold-test --strict
```

Result:

```text
Scaffold created successfully
HIGH=0, MEDIUM=0, LOW=0
Generated scaffold Python syntax: PASS
```

### 4. Source-level API verification

Current imports, constructors, and patterns were checked against the pinned Agno repository and official cookbooks, including:

- `Agent`, `Team`, `Step`, `Workflow`;
- `AgentOS.get_app()` and `AgentOS.serve()` patterns;
- `AgentOS(mcp=...)` and `MCPConfig`;
- `AuthorizationConfig(user_isolation=True)`;
- `RunContext.user_id/session_id/session_state`;
- `MemoryManager`, automatic memory, Knowledge/Chroma, structured output;
- `AccuracyEval`, `ReliabilityEval`, vLLM, HITL tools;
- Agno `LocalSkills`/`Skills` loading.

## Environment limitation

A clean installation of `agno[os,openai,postgres,mcp]==3.0.5` could not be downloaded in the execution container because outbound DNS/PyPI resolution was unavailable. Therefore, this report does **not** claim a live model call, live PostgreSQL migration, live AgentOS HTTP request, or live MCP handshake. Those runtime gates are included in `references/14-testing-checklists.md` and the production template README for execution in the target environment.

## Recommended target-environment gate

```bash
cd templates/production_agentos
cp .env.example .env
uv sync --extra dev
docker compose up -d postgres
set -a; . ./.env; set +a
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run agno-app
curl -fsS http://localhost:7777/health
curl -fsS http://localhost:7777/openapi.json >/dev/null
```

Then run the supplied HTTP requests, cross-user isolation cases, HITL continuation, tracing inspection, evals, and load tests before production release.
