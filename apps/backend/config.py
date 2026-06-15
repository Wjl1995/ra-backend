from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Settings:
    app_name: str = os.getenv("APP_NAME", "ReActAgent Backend")
    api_prefix: str = "/api/v1"
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/db.sqlite3")
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me")
    jwt_algorithm: str = "HS256"
    daily_quota: int = int(os.getenv("DAILY_QUOTA", "50"))
    upload_dir: str = os.getenv("UPLOAD_DIR", "./data/uploads")
    cors_origins: tuple[str, ...] = ("*",)


settings = Settings()
