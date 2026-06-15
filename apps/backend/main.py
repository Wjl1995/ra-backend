from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.backend.admin_views import register_admin_routes
from apps.backend.api.auth import router as auth_router
from apps.backend.api.chat import router as chat_router
from apps.backend.api.document import router as document_router
from apps.backend.api.me import router as me_router
from apps.backend.api.search import router as search_router
from apps.backend.api.suggestions import router as suggestions_router
from apps.backend.config import settings
from apps.backend.database import Base, engine
from apps.backend.version import APP_NAME, API_VERSION


def create_app() -> FastAPI:
    app = FastAPI(title=APP_NAME, version=API_VERSION)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api_prefix = settings.api_prefix
    app.include_router(auth_router, prefix=api_prefix)
    app.include_router(me_router, prefix=api_prefix)
    app.include_router(chat_router, prefix=api_prefix)
    app.include_router(document_router, prefix=api_prefix)
    app.include_router(search_router, prefix=api_prefix)
    app.include_router(suggestions_router, prefix=api_prefix)
    register_admin_routes(app)

    @app.on_event("startup")
    def on_startup() -> None:
        Base.metadata.create_all(bind=engine)

    @app.get("/health")
    def health():
        return {"status": "ok", "service": APP_NAME}

    return app


app = create_app()
