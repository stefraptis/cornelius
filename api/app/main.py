"""FastAPI application factory."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import db
from app.config import get_settings
from app.logging_setup import configure_logging, request_id_var
from app.routers import health, me, procedures

log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn, environment=settings.app_env, send_default_pii=False
        )
    log.info("app.start", extra={"ctx_env": settings.app_env})
    yield
    db.close_pool()
    log.info("app.stop")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=f"{settings.app_name} API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-Id"] = request_id
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        if request.url.path not in ("/health", "/health/db"):
            log.info(
                "http.request",
                extra={
                    "ctx_method": request.method,
                    "ctx_path": request.url.path,
                    "ctx_status": response.status_code,
                    "ctx_ms": duration_ms,
                },
            )
        return response

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("http.unhandled", extra={"ctx_path": request.url.path})
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Something went wrong. Try again, and contact support if it persists."
            },
        )

    app.include_router(health.router)
    app.include_router(me.router)
    app.include_router(procedures.router)
    return app


app = create_app()
