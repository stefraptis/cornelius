from __future__ import annotations

import logging

from fastapi import APIRouter, Response, status

from app import db
from app.config import get_settings

log = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    settings = get_settings()
    return {
        "app": settings.app_name,
        "health": "/health",
        "database": "/health/db",
        "docs": "/docs" if not settings.is_production else "",
    }


@router.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}


@router.get("/health/db")
def health_db(response: Response) -> dict[str, str]:
    settings = get_settings()
    try:
        ok = db.ping()
        reason = ""
    except Exception as exc:  # noqa: BLE001
        log.exception("health.db_unreachable")
        ok = False
        # The server's message helps in development (wrong password, host,
        # SSL); it never includes the password itself.
        reason = str(exc).splitlines()[0][:300] if not settings.is_production else ""
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable", "reason": reason}
    return {"status": "ok"}
