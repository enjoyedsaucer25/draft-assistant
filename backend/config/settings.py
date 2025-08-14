# backend/config/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional

class Settings(BaseSettings):
    db_url: str = "sqlite:///./draft.db"
    cors_origins: List[str] = ["*"]      # later: restrict to your UI origin(s)
    admin_token: Optional[str] = None    # set DA_ADMIN_TOKEN to guard /admin/*

    # pydantic v2 settings config
    model_config = SettingsConfigDict(
        env_prefix="DA_",
        case_sensitive=False,
        env_file=".env",                 # <-- read .env at project root
        env_file_encoding="utf-8",
    )

settings = Settings()
