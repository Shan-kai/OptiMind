"""Configuration management. Tunables come from env vars / config file."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from env vars / .env file.

    All values are overridable via the OPTI_MIND_ env prefix.
    """

    model_config = SettingsConfigDict(
        env_prefix="OPTI_MIND_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    env: str = "local"
    app_name: str = "OptiMind"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"

    # CORS
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    # Upload cleanup
    upload_ttl_seconds: int = 86400

    # LLM (single provider, shared across all layers)
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_timeout: float = 90.0
    llm_temperature: float = 0.1

    # Per-layer LLM switches (Deterministic First: off by default)
    llm_schema_interpreter: bool = False
    llm_model_generator: bool = False
    llm_decision_analyzer: bool = True

    # Agentic decision analysis: LLM answers post-solution questions via tools
    llm_decision_analyzer_agent: bool = True
    llm_decision_analyzer_max_tool_turns: int = 10

    # Single LLM orchestrator that controls mapping + parameters + pipeline
    llm_orchestrator_agent: bool = False
    llm_orchestrator_max_tool_turns: int = 15
    llm_orchestrator_sample_rows: int = 5

    # Session logging
    session_log_dir: str = "sessions"

    # Checkpoint persistence: use SQLite so sessions survive server reloads
    persist_checkpoints: bool = False

    # Solver
    solver_backend: str = "cplex"
    solver_timeout: float = 300.0
    cplex_bin_dir: str = ""
    cplex_license_path: str = ""
    cplex_log_output: bool = False

    # Knowledge
    knowledge_match_threshold: float = 0.6


@lru_cache
def get_settings() -> Settings:
    """Return the singleton Settings (cached for DI and test overrides)."""
    return Settings()


def configure_cplex_env() -> None:
    """Ensure CPLEX native DLLs are findable at runtime.

    Reads cplex_bin_dir from settings; if non-empty, prepends it to PATH.
    Safe to call even when CPLEX is not used.
    """
    import os

    settings = get_settings()
    if settings.cplex_bin_dir:
        current = os.environ.get("PATH", "")
        if settings.cplex_bin_dir not in current:
            os.environ["PATH"] = f"{settings.cplex_bin_dir};{current}"
    if settings.cplex_license_path:
        os.environ.setdefault("CPLEX_LICENSE_FILE", settings.cplex_license_path)
