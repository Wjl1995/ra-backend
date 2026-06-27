from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_project_path(raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def _resolve_sqlite_url(database_url: str) -> str:
    if database_url in {"sqlite:///:memory:", "sqlite://"}:
        return database_url
    if database_url.startswith("sqlite:////"):
        return database_url
    if database_url.startswith("sqlite:///"):
        path_part = database_url.removeprefix("sqlite:///")
        if Path(path_part).is_absolute():
            return database_url
        return f"sqlite:///{_resolve_project_path(path_part)}"
    return database_url


@dataclass
class Settings:
    app_name: str = os.getenv("APP_NAME", "ReActAgent Backend")
    api_prefix: str = "/api/v1"
    database_url: str = _resolve_sqlite_url(os.getenv("DATABASE_URL", "sqlite:///./data/db.sqlite3"))
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me")
    jwt_algorithm: str = "HS256"
    wechat_login_mode: str = os.getenv("WECHAT_LOGIN_MODE", "mock").lower()
    wechat_app_id: str = os.getenv("WECHAT_APP_ID", "")
    wechat_app_secret: str = os.getenv("WECHAT_APP_SECRET", "")
    wechat_api_timeout_seconds: float = float(os.getenv("WECHAT_API_TIMEOUT_SECONDS", "10"))
    daily_quota: int = int(os.getenv("DAILY_QUOTA", "50"))
    upload_dir: str = str(_resolve_project_path(os.getenv("UPLOAD_DIR", "./data/uploads")))
    user_export_dir: str = str(_resolve_project_path(os.getenv("USER_EXPORT_DIR", "./data/user_exports")))
    kimi_api_key: str = os.getenv("KIMI_API_KEY", "")
    kimi_base_url: str = os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
    kimi_model: str = os.getenv("KIMI_MODEL", "moonshot-v1-8k")
    kimi_max_tokens: int = int(os.getenv("KIMI_MAX_TOKENS", "1024"))
    kimi_timeout_seconds: float = float(os.getenv("KIMI_TIMEOUT_SECONDS", "60"))
    kimi_max_context_messages: int = int(os.getenv("KIMI_MAX_CONTEXT_MESSAGES", "12"))
    agent_tool_mode: str = os.getenv("AGENT_TOOL_MODE", "mcp").lower()
    mcp_server_config_json: str = os.getenv("MCP_SERVER_CONFIG_JSON", "")
    agent_max_tool_calls: int = int(os.getenv("AGENT_MAX_TOOL_CALLS", "4"))
    retrieval_top_k: int = int(os.getenv("RETRIEVAL_TOP_K", "4"))
    retrieval_chunk_size: int = int(os.getenv("RETRIEVAL_CHUNK_SIZE", "600"))
    retrieval_chunk_overlap: int = int(os.getenv("RETRIEVAL_CHUNK_OVERLAP", "120"))
    cors_origins: tuple[str, ...] = ("*",)


settings = Settings()


def ensure_runtime_directories() -> None:
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.user_export_dir).mkdir(parents=True, exist_ok=True)

    if not settings.database_url.startswith("sqlite:///"):
        return

    database_path = Path(settings.database_url.removeprefix("sqlite:///"))
    if str(database_path) == ":memory:":
        return

    database_path.parent.mkdir(parents=True, exist_ok=True)


ensure_runtime_directories()
