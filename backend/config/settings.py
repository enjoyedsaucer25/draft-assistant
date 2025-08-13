from pydantic import BaseSettings
from typing import List, Optional

class Settings(BaseSettings):
    db_url: str = "sqlite:///./draft.db"
    cors_origins: List[str] = ["*"]      # later: restrict to your UI origin
    admin_token: Optional[str] = None    # set DA_ADMIN_TOKEN in env to guard /admin/*

    class Config:
        env_prefix = "DA_"
        case_sensitive = False

settings = Settings()
