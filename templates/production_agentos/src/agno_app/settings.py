"""Environment-backed settings with production safety checks."""

from __future__ import annotations

import os
from dataclasses import dataclass


TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    raise ValueError(f"{name} must be one of {sorted(TRUE_VALUES | FALSE_VALUES)}")


def _get_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.getenv(name)
    value = default if raw is None else int(raw)
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def _get_list(name: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None:
        return default
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _optional(name: str) -> str | None:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return None
    return raw.strip()


@dataclass(frozen=True, slots=True)
class Settings:
    app_env: str
    host: str
    port: int
    database_url: str
    model_provider: str
    model_id: str
    model_base_url: str | None
    model_api_key: str | None
    memory_enabled: bool
    history_runs: int
    authorization_enabled: bool
    jwt_algorithm: str
    jwt_audience: str | None
    jwt_verification_key: str | None
    cors_allowed_origins: tuple[str, ...]
    tracing_enabled: bool
    mcp_enabled: bool
    mcp_allowed_hosts: tuple[str, ...]
    agno_telemetry: bool

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls(
            app_env=os.getenv("APP_ENV", "development").strip().lower(),
            host=os.getenv("APP_HOST", "0.0.0.0").strip(),
            port=_get_int("APP_PORT", 7777, minimum=1),
            database_url=os.getenv(
                "DATABASE_URL",
                "postgresql+psycopg://agno:agno@localhost:5432/agno",
            ).strip(),
            model_provider=os.getenv("MODEL_PROVIDER", "openai").strip().lower(),
            model_id=os.getenv("MODEL_ID", "gpt-5.5").strip(),
            model_base_url=_optional("MODEL_BASE_URL"),
            model_api_key=_optional("MODEL_API_KEY"),
            memory_enabled=_get_bool("MEMORY_ENABLED", False),
            history_runs=_get_int("HISTORY_RUNS", 8, minimum=0),
            authorization_enabled=_get_bool("AUTHORIZATION_ENABLED", False),
            jwt_algorithm=os.getenv("JWT_ALGORITHM", "RS256").strip(),
            jwt_audience=_optional("JWT_AUDIENCE"),
            jwt_verification_key=(
                _optional("JWT_VERIFICATION_KEY").replace("\\n", "\n")
                if _optional("JWT_VERIFICATION_KEY")
                else None
            ),
            cors_allowed_origins=_get_list(
                "CORS_ALLOWED_ORIGINS",
                ("http://localhost:3000",),
            ),
            tracing_enabled=_get_bool("TRACING_ENABLED", True),
            mcp_enabled=_get_bool("MCP_ENABLED", False),
            mcp_allowed_hosts=_get_list(
                "MCP_ALLOWED_HOSTS",
                ("localhost", "127.0.0.1"),
            ),
            agno_telemetry=_get_bool("AGNO_TELEMETRY", False),
        )
        settings.validate()
        return settings

    @property
    def is_production(self) -> bool:
        return self.app_env in {"production", "prod"}

    def validate(self) -> None:
        if not self.database_url:
            raise ValueError("DATABASE_URL is required")
        if not self.model_id:
            raise ValueError("MODEL_ID is required")
        if self.model_provider not in {"openai", "vllm", "openai-like"}:
            raise ValueError("MODEL_PROVIDER must be openai, vllm, or openai-like")
        if self.model_provider == "openai-like" and not self.model_base_url:
            raise ValueError("MODEL_BASE_URL is required for openai-like")
        if self.is_production and not self.authorization_enabled:
            raise ValueError("AUTHORIZATION_ENABLED must be true in production")
        if self.authorization_enabled and not self.jwt_verification_key:
            raise ValueError("JWT_VERIFICATION_KEY is required when authorization is enabled")
        if self.memory_enabled and self.is_production and not self.authorization_enabled:
            raise ValueError("Production memory requires authenticated user identity")
        if self.is_production and any(origin == "*" for origin in self.cors_allowed_origins):
            raise ValueError("Wildcard CORS is not allowed in production")


settings = Settings.from_env()
