"""Safe defaults for import/smoke tests."""

import os


os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://agno:agno@localhost:5432/agno_test",
)
os.environ.setdefault("MODEL_PROVIDER", "openai")
os.environ.setdefault("MODEL_ID", "gpt-5.5")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("AUTHORIZATION_ENABLED", "false")
os.environ.setdefault("MEMORY_ENABLED", "false")
os.environ.setdefault("TRACING_ENABLED", "false")
os.environ.setdefault("MCP_ENABLED", "false")
os.environ.setdefault("AGNO_TELEMETRY", "false")
