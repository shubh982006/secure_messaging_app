"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import (
    attachments,
    auth,
    contacts,
    conversations,
    messages,
    users,
)
from app.core.config import settings
from app.core.errors import AppError
from app.db.session import dispose_engine
from app.services import attachment_service
from app.ws.gateway import websocket_endpoint
from app.ws.manager import connection_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("signal")


@asynccontextmanager
async def lifespan(_: FastAPI):
    import asyncio

    from app.db.bootstrap import prepare_database
    from app.services.message_service import run_expiry_sweeper

    await prepare_database()

    # Disappearing messages: expiry is enforced at query time, and this loop
    # reclaims the rows and notifies open clients.
    sweeper = asyncio.create_task(
        run_expiry_sweeper(settings.disappear_sweep_seconds)
    )
    try:
        yield
    finally:
        sweeper.cancel()
        try:
            await sweeper
        except asyncio.CancelledError:
            pass
        await dispose_engine()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=(
        "Signal clone API - mocked OTP auth, 1:1 and group messaging over "
        "WebSockets, high-water-mark receipts, typing and presence."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# Auth rides on the Authorization header, not cookies, so credentialed CORS is
# unnecessary - which is what lets a wildcard origin work at all.
_origins = settings.cors_origin_list
_wildcard = "*" in _origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    # Preview deployments get fresh subdomains on every push; allow them all.
    allow_origin_regex=None if _wildcard else r"https://.*\.vercel\.app",
    allow_credentials=not _wildcard,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# --------------------------------------------------------------------------- #
# error handling - one envelope shape for every failure (see API_CONTRACT.md)
# --------------------------------------------------------------------------- #
@app.exception_handler(AppError)
async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request failed validation",
                "detail": {"errors": _safe_errors(exc)},
            }
        },
    )


def _safe_errors(exc: RequestValidationError) -> list[dict]:
    cleaned = []
    for error in exc.errors():
        cleaned.append(
            {
                "loc": [str(part) for part in error.get("loc", [])],
                "msg": error.get("msg", ""),
                "type": error.get("type", ""),
            }
        )
    return cleaned


@app.exception_handler(StarletteHTTPException)
async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    codes = {401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND", 429: "RATE_LIMITED"}
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": codes.get(exc.status_code, "HTTP_ERROR"),
                "message": str(exc.detail),
                "detail": {},
            }
        },
    )


@app.exception_handler(Exception)
async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:  # pragma: no cover
    logger.exception("unhandled error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Something went wrong",
                "detail": {},
            }
        },
    )


# --------------------------------------------------------------------------- #
# routes
# --------------------------------------------------------------------------- #
for router in (
    auth.router,
    users.router,
    contacts.router,
    conversations.router,
    messages.router,
    attachments.router,
):
    app.include_router(router, prefix=settings.api_prefix)

# Uploaded attachments are served straight off disk. In production this sits
# behind the same volume as the database (or is replaced by object storage).
_media = attachment_service.media_dir()
app.mount(
    settings.media_url_prefix,
    StaticFiles(directory=str(_media)),
    name="media",
)


@app.websocket(f"{settings.api_prefix}/ws")
async def ws(websocket: WebSocket, token: str | None = None) -> None:
    await websocket_endpoint(websocket, token)


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {
        "status": "ok",
        "service": settings.app_name,
        "live_sockets": getattr(connection_manager, "connection_count", lambda: 0)(),
        "online_users": len(connection_manager.online_users()),
    }


@app.get("/", tags=["ops"])
async def root() -> dict:
    return {
        "service": settings.app_name,
        "docs": "/docs",
        "health": "/health",
        "api": settings.api_prefix,
        "websocket": f"{settings.api_prefix}/ws?token=<access_token>",
    }
