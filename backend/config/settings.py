# backend/config/settings.py
from __future__ import annotations
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Core
    db_url: str = "sqlite:///./draft.db"
    cors_origins: List[str] = ["*"]
    admin_token: Optional[str] = None

    # Feature flags
    enable_fp_imports: bool = False  # gate FantasyPros routes

    # Debug (used by backend/run_debug.py)
    debug_port: Optional[int] = None         # maps from DA_DEBUG_PORT
    debug_wait: bool = False                 # maps from DA_DEBUG_WAIT (0/1/true/false)

    # pydantic v2 settings config
    model_config = SettingsConfigDict(
        env_prefix="DA_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # ignore unknown DA_* keys instead of raising
    )


settings = Settings()
