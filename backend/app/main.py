import asyncio
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
from app.core.event_bus import EventBus
from app.core.logging import AUDIT_QUEUE_MAX_SIZE, AuditLogHandler, AuditQueue, configure_logging
from app.repositories.events import EventRepository
from app.repositories.matches import MatchRepository
from app.repositories.users import UserRepository
from app.services import game_engine
from app.services.audit import AuditService
from app.services.auth import AuthService
from app.services.game_engine import GameEngineService
from app.services.game_handlers import GameHandlers, MatchFinisher
from app.services.invite_handlers import InviteHandlers
from app.services.invite_service import InviteService
from app.services.ranking import RankingService
from app.ws.connection_manager import connection_manager
from app.ws.gateway import router as ws_router

INTERNAL_ERROR_MESSAGE = "Erro interno."

logger = logging.getLogger(__name__)

type Audit = tuple[AuditLogHandler, AuditService]


async def _start_audit(repository: EventRepository) -> Audit:
    await repository.ensure_indexes()
    queue: AuditQueue = asyncio.Queue(maxsize=AUDIT_QUEUE_MAX_SIZE)
    handler = AuditLogHandler()
    handler.bind(asyncio.get_running_loop(), queue)
    logging.getLogger().addHandler(handler)
    service = AuditService(repository, queue)
    service.start()
    return handler, service


async def _stop_audit(audit: Audit) -> None:
    handler, service = audit
    logging.getLogger().removeHandler(handler)
    handler.unbind()
    await service.stop()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    configure_logging(settings.log_level)

    client = create_client(settings.mongo_uri)
    app.state.mongo_client = client

    db = client[settings.mongo_db]
    users = UserRepository(db)
    match_repo = MatchRepository(db)
    events = EventRepository(db)

    app.state.user_repository = users
    app.state.match_repository = match_repo

    auth_service = AuthService(
        users, settings.jwt_secret.get_secret_value(), settings.jwt_expires_minutes
    )
    ranking_service = RankingService(users)

    app.state.auth_service = auth_service
    app.state.ranking_service = ranking_service

    event_bus = EventBus()
    app.state.event_bus = event_bus
    finisher = MatchFinisher(connection_manager, ranking_service, match_repo)
    engine = GameEngineService(
        on_match_end=finisher.finish,
        turn_timeout_seconds=game_engine.TURN_TIMEOUT_SECONDS,
        reconnect_grace_seconds=settings.reconnect_grace_s,
    )
    app.state.game_engine = engine
    handlers = GameHandlers(engine, finisher, connection_manager, settings.reconnect_grace_s)
    handlers.subscribe(event_bus)
    invite_service = InviteService(engine, connection_manager, settings.invite_timeout_s)
    InviteHandlers(invite_service).subscribe(event_bus)

    db_available = await ping(client)
    if db_available:
        await users.ensure_indexes()
    audit = await _start_audit(events) if settings.audit_enabled and db_available else None
    db_status = "ok" if db_available else "error"
    logger.info("server.started", extra={"details": {"version": __version__, "db": db_status}})
    try:
        yield
    finally:
        engine.close()
        invite_service.close()
        logger.info("server.stopped", extra={"details": {"version": __version__}})
        if audit is not None:
            await _stop_audit(audit)
        await client.close()


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
    app.include_router(matches_router)
    app.include_router(ws_router)

    return app
