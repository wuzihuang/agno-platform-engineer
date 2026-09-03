"""AgentOS application entry point."""

from __future__ import annotations

import uvicorn

from agno.os import AgentOS
from agno.os.config import AuthorizationConfig, MCPConfig

from agno_app.agent import assistant
from agno_app.db import db
from agno_app.settings import settings


def _authorization_config() -> AuthorizationConfig | None:
    if not settings.authorization_enabled:
        return None
    assert settings.jwt_verification_key is not None  # validated by Settings
    return AuthorizationConfig(
        verification_keys=[settings.jwt_verification_key],
        algorithm=settings.jwt_algorithm,
        verify_audience=bool(settings.jwt_audience),
        audience=settings.jwt_audience,
        admin_scope="agent_os:admin",
        user_isolation=True,
    )


def _mcp_config() -> MCPConfig | bool:
    if not settings.mcp_enabled:
        return False
    return MCPConfig(
        default_tools=True,
        result_mode="trimmed",
        allowed_hosts=list(settings.mcp_allowed_hosts),
    )


agent_os = AgentOS(
    id="support-agent-os-v1",
    name="Support AgentOS",
    description="Production-oriented Agno AgentOS starter",
    db=db,
    agents=[assistant],
    authorization=settings.authorization_enabled,
    authorization_config=_authorization_config(),
    cors_allowed_origins=list(settings.cors_allowed_origins),
    mcp=_mcp_config(),
    tracing=settings.tracing_enabled,
    telemetry=settings.agno_telemetry,
)

app = agent_os.get_app()


def main() -> None:
    uvicorn.run(
        "agno_app.app:app",
        host=settings.host,
        port=settings.port,
        reload=not settings.is_production,
    )


if __name__ == "__main__":
    main()
