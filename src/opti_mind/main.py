"""FastAPI application entrypoint.

API layer only handles routing, validation and dispatching.
No business logic lives here.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from opti_mind.api.middleware import RequestContextMiddleware
from opti_mind.api.routes import router as optimize_router
from opti_mind.api.sessions import UPLOAD_DIR, cleanup_old_uploads
from opti_mind.api.sessions import router as sessions_router
from opti_mind.config import get_settings
from opti_mind.core.exceptions import register_exception_handlers
from opti_mind.logging_setup import setup_logging
from opti_mind.solver.backends import DEFAULT_REGISTRY

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """应用启动时初始化日志、清理过期上传等一次性配置。"""
    settings = get_settings()
    setup_logging(settings.log_level)
    cleanup_old_uploads(UPLOAD_DIR, settings.upload_ttl_seconds)
    _warn_if_solver_backend_unavailable()
    yield


def _warn_if_solver_backend_unavailable() -> None:
    """如果配置的后端不可用，打印 warn 日志提示用户切换，但不阻塞启动。"""
    settings = get_settings()
    available = DEFAULT_REGISTRY.list_available()
    if settings.solver_backend not in available:
        logger.warning(
            "OPTI_MIND_SOLVER_BACKEND=%s is configured but %s is not available. "
            "Available backends: %s. Switch via OPTI_MIND_SOLVER_BACKEND=...",
            settings.solver_backend,
            settings.solver_backend,
            available,
        )


app = FastAPI(
    title="OptiMind",
    description=(
        "Optimization Copilot - AI-native Decision Intelligence " "Platform for Operations Research"
    ),
    version="0.1.0",
    lifespan=_lifespan,
)

app.add_middleware(RequestContextMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(optimize_router)
app.include_router(sessions_router)


@app.get("/api/v1/health", tags=["system"])
def health() -> dict[str, str | list[str]]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "version": "0.1.0",
        "available_solver_backends": DEFAULT_REGISTRY.list_available(),
    }
