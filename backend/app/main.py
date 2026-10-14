import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app import __version__
from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.matches import router as matches_router
from app.api.me import router as me_router
from app.api.ranking import router as ranking_router
from app.core.config import Settings
from app.core.database import create_client, ping
from app.core.event_bus import event_bus
from app.core.logging import configure_logging
from app.repositories.matches import MatchRepository
from app.repositories.users import UserRepository
from app.services.auth import AuthService
from app.services.game_handlers import setup_game_handlers
from app.services.matchmaking_handlers import setup_matchmaking_handlers
from app.services.ranking import RankingService
from app.ws.connection_manager import connection_manager
from app.ws.gateway import router as ws_router

INTERNAL_ERROR_MESSAGE = "Erro interno."

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    configure_logging(settings.log_level)
    
    # Inicializa os ouvintes do EventBus para o Matchmaking
    setup_matchmaking_handlers()
    setup_game_handlers() 
    
    client = create_client(settings.mongo_uri)
    app.state.mongo_client = client

    # Registra o event_bus no estado global da aplicação
    app.state.event_bus = event_bus

    db = client[settings.mongo_db]
    users = UserRepository(db)
    match_repo = MatchRepository(db)

    app.state.user_repository = users
    app.state.match_repository = match_repo

    auth_service = AuthService(
        users, settings.jwt_secret.get_secret_value(), settings.jwt_expires_minutes
    )
    ranking_service = RankingService(users)

    app.state.auth_service = auth_service
    app.state.ranking_service = ranking_service

    # Injeta referências no connection_manager para o encerramento da partida
    connection_manager.match_repo = match_repo
    connection_manager.ranking_service = ranking_service

    db_available = await ping(client)
    if db_available:
        await users.ensure_indexes()
    db_status = "ok" if db_available else "error"
    logger.info(
        "server.started", extra={"details": {"version": __version__, "db": db_status}}
    )
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
    app = FastAPI(
        title="Jogo da Velha Multiplayer", version=__version__, lifespan=lifespan
    )
    app.state.settings = settings or Settings()
    app.add_exception_handler(Exception, handle_unexpected_error)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(me_router)
    app.include_router(ranking_router)
    app.include_router(matches_router)
    app.include_router(ws_router)

    return app