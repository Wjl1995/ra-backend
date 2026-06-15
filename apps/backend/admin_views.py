from __future__ import annotations

from fastapi import FastAPI


def register_admin_routes(app: FastAPI) -> None:
    @app.get("/admin")
    def admin_index():
        return {"message": "Admin scaffold is ready", "sqladmin": "pending"}
