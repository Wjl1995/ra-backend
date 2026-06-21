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
    kimi_api_key: str = os.getenv("KIMI_API_KEY", "")
    kimi_base_url: str = os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
    kimi_model: str = os.getenv("KIMI_MODEL", "moonshot-v1-8k")
    kimi_max_tokens: int = int(os.getenv("KIMI_MAX_TOKENS", "1024"))
    kimi_timeout_seconds: float = float(os.getenv("KIMI_TIMEOUT_SECONDS", "60"))
    kimi_max_context_messages: int = int(os.getenv("KIMI_MAX_CONTEXT_MESSAGES", "12"))
    retrieval_top_k: int = int(os.getenv("RETRIEVAL_TOP_K", "4"))
    retrieval_chunk_size: int = int(os.getenv("RETRIEVAL_CHUNK_SIZE", "600"))
    retrieval_chunk_overlap: int = int(os.getenv("RETRIEVAL_CHUNK_OVERLAP", "120"))
    cors_origins: tuple[str, ...] = ("*",)


settings = Settings()
