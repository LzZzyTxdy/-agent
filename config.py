"""Centralized environment-backed application configuration."""

from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables and .env."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    target_url: str = "about:blank"
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model: Optional[str] = None

    agent_mode: Literal["auto", "manual", "dry_run"] = "manual"
    solver_type: Literal["llm", "mock"] = "llm"
    mock_mode: Literal["manual", "random"] = "manual"
    min_confidence: float = Field(default=0.70, ge=0.0, le=1.0)
    low_confidence_mode: Literal["manual", "retry", "accept", "stop"] = "manual"

    headless: bool = False
    browser_channel: Optional[str] = "chrome"
    page_timeout_ms: int = Field(default=15000, ge=1000)
    llm_timeout_seconds: float = Field(default=60.0, gt=0)
    llm_max_retries: int = Field(default=3, ge=1, le=10)
    browser_max_retries: int = Field(default=3, ge=1, le=10)
    cache_path: Path = PROJECT_DIR / "data" / "question_cache_rag.json"
    runs_dir: Path = PROJECT_DIR / "runs"

    enable_local_retrieval: bool = True
    reference_pdf_glob: str = "*.pdf"
    pdf_index_path: Path = PROJECT_DIR / "data" / "pdf_index.json"
    retrieval_chunk_chars: int = Field(default=1200, ge=300, le=5000)
    retrieval_top_k: int = Field(default=4, ge=1, le=10)
    retrieval_max_context_chars: int = Field(default=7000, ge=1000, le=30000)
    local_retrieval_min_score: float = Field(default=12.0, ge=0)
    web_search_mode: Literal["off", "auto", "always"] = "auto"
    web_search_max_results: int = Field(default=3, ge=1, le=10)
    web_search_timeout_seconds: int = Field(default=8, ge=2, le=30)
    web_search_backend: str = "startpage"
    web_search_cache_path: Path = PROJECT_DIR / "data" / "web_search_cache.json"

    @field_validator("browser_channel", mode="before")
    def empty_channel_to_none(cls, value: object) -> object:
        return None if value == "" else value

    def require_llm(self, force: bool = False) -> None:
        if self.solver_type != "llm" and not force:
            return
        missing = [
            name
            for name, value in (
                ("LLM_API_KEY", self.llm_api_key),
                ("LLM_MODEL", self.llm_model),
            )
            if not value
        ]
        if missing:
            from exceptions import ConfigurationError

            raise ConfigurationError("Missing LLM configuration: " + ", ".join(missing))
