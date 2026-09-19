"""
CycloneShield Configuration Settings
=====================================
Loads environment variables and provides typed, validated configuration
using pydantic-settings. All secrets must be in .env; never hardcode.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root (one level up from config/)
PROJECT_ROOT = Path(__file__).parent.parent


class Settings(BaseSettings):
    """Typed, validated application settings loaded from environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Gemini ----
    gemini_api_key: Optional[str] = Field(default=None, description="Gemini API key")
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        description="Gemini model name (env: GEMINI_MODEL)",
    )
    # Fallback list tried in order if primary model fails
    gemini_model_fallbacks: list[str] = Field(
        default=["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro"],
        description="Fallback model list",
    )

    # ---- GEE ----
    gee_service_account: Optional[str] = Field(
        default=None, description="GEE service account email"
    )
    gee_private_key_file: Optional[str] = Field(
        default=None, description="Path to GEE service account JSON"
    )
    gee_project: Optional[str] = Field(
        default=None, description="GEE cloud project ID"
    )

    # ---- Telegram ----
    telegram_bot_token: Optional[str] = Field(
        default=None, description="Telegram bot token"
    )
    telegram_test_chat_id: Optional[str] = Field(
        default=None, description="Test Telegram chat ID"
    )
    dry_run: bool = Field(
        default=True, description="Dry-run mode: log dispatch without sending"
    )

    # ---- Backend ----
    backend_port: int = Field(default=8000, description="FastAPI port")
    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        description="CORS allowed origins (comma-separated)",
    )

    # ---- Pipeline paths ----
    processed_dir: Path = Field(
        default=PROJECT_ROOT / "data" / "processed",
        description="Directory for cached processed outputs",
    )
    raw_dir: Path = Field(
        default=PROJECT_ROOT / "data" / "raw",
        description="Directory for raw downloaded data",
    )

    # ---- Scenario ----
    default_scenario: str = Field(
        default="fani_2019", description="Default scenario name"
    )

    @field_validator("processed_dir", "raw_dir", mode="before")
    @classmethod
    def resolve_path(cls, v: str | Path) -> Path:
        """Resolve relative paths relative to the project root."""
        p = Path(v)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p

    @property
    def cors_origins_list(self) -> list[str]:
        """Return CORS origins as a list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def ensure_dirs(self) -> None:
        """Create data directories if they don't exist."""
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)


# Module-level singleton (lazy instantiation)
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Return the global settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_dirs()
    return _settings
