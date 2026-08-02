from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from apps.backend.config import ensure_runtime_directories, settings


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


ensure_runtime_directories()

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if _is_sqlite(settings.database_url) else {},
)

# ── SQLite WAL 模式 ──────────────────────────────────────────────
# WAL 允许读写并发（读不阻塞写，写不阻塞读），配合 busy_timeout
# 解决 API 线程与 Worker 线程同时访问 SQLite 的锁竞争问题。
if _is_sqlite(settings.database_url):

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
