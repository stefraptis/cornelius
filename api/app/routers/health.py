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
    try:
        ok = db.ping()
    except Exception:  # noqa: BLE001
        log.exception("health.db_unreachable")
        ok = False
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable"}
    return {"status": "ok"}
