import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app import __version__
from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.me import router as me_router
from app.api.ranking import router as ranking_router
from app.core.config import Settings
from app.core.database import create_client, ping
from app.core.logging import configure_logging
from app.repositories.users import UserRepository
from app.services.auth import AuthService
from app.services.ranking import RankingService

INTERNAL_ERROR_MESSAGE = "Erro interno."

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    configure_logging(settings.log_level)
    client = create_client(settings.mongo_uri)
    app.state.mongo_client = client
    users = UserRepository(client[settings.mongo_db])
    app.state.auth_service = AuthService(
        users, settings.jwt_secret.get_secret_value(), settings.jwt_expires_minutes
    )
    app.state.ranking_service = RankingService(users)
    db_available = await ping(client)
    if db_available:
        await users.ensure_indexes()
    db_status = "ok" if db_available else "error"
    logger.info("server.started", extra={"details": {"version": __version__, "db": db_status}})
    try:
        yield
    finally:
        await client.close()
        logger.info("server.stopped", extra={"details": {"version": __version__}})


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    route = request.scope.get("route")
    details = {
        "method": request.method,
        "route": getattr(route, "path", request.url.path),
        "exception": type(exc).__name__,
    }
    logger.error("error.internal", extra={"details": details}, exc_info=exc)
    return JSONResponse(
        {"detail": INTERNAL_ERROR_MESSAGE},
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Jogo da Velha Multiplayer", version=__version__, lifespan=lifespan)
    app.state.settings = settings or Settings()
    app.add_exception_handler(Exception, handle_unexpected_error)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(me_router)
    app.include_router(ranking_router)
    return app
