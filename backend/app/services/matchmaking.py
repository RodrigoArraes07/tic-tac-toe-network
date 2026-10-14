import asyncio
import logging
import uuid
from dataclasses import dataclass

from app.domain.enums import Symbol
from app.ws.connection_manager import connection_manager
from app.ws.protocol import MatchFoundPayload, OpponentInfo, WSMessageEnvelope
from app.services.game_engine import game_engine_service

logger = logging.getLogger(__name__)


@dataclass
class QueuePlayer:
    user_id: str
    username: str


class MatchmakingService:
    def __init__(self) -> None:
        self._queue: list[QueuePlayer] = []
        self._lock = asyncio.Lock()

    async def add_player(self, user_id: str, username: str) -> bool:
        async with self._lock:
            if any(p.user_id == user_id for p in self._queue):
                return False

            player = QueuePlayer(user_id=user_id, username=username)
            self._queue.append(player)
            logger.info(
                "matchmaking.player_joined",
                extra={"details": {"user_id": user_id, "queue_size": len(self._queue)}},
            )

            if len(self._queue) >= 2:
                p1 = self._queue.pop(0)
                p2 = self._queue.pop(0)
                asyncio.create_task(self._create_match(p1, p2))

            return True

    async def remove_player(self, user_id: str) -> bool:
        async with self._lock:
            initial_len = len(self._queue)
            self._queue = [p for p in self._queue if p.user_id != user_id]
            removed = len(self._queue) < initial_len
            if removed:
                logger.info(
                    "matchmaking.player_left",
                    extra={"details": {"user_id": user_id, "queue_size": len(self._queue)}},
                )
            return removed

    async def _create_match(self, p1: QueuePlayer, p2: QueuePlayer) -> None:
        match_id = str(uuid.uuid4())

        await game_engine_service.create_match(
            match_id=match_id,
            p1_id=p1.user_id,
            p1_username=p1.username,
            p2_id=p2.user_id,
            p2_username=p2.username,
        )

        msg_p1 = WSMessageEnvelope(
            type="MATCH_FOUND",
            payload=MatchFoundPayload(
                match_id=match_id,
                symbol=Symbol.X,
                opponent=OpponentInfo(id=p2.user_id, username=p2.username),
            ).model_dump(),
        )

        msg_p2 = WSMessageEnvelope(
            type="MATCH_FOUND",
            payload=MatchFoundPayload(
                match_id=match_id,
                symbol=Symbol.CIRCLE,
                opponent=OpponentInfo(id=p1.user_id, username=p1.username),
            ).model_dump(),
        )

        await asyncio.gather(
            connection_manager.send_personal_message(p1.user_id, msg_p1.model_dump_json()),
            connection_manager.send_personal_message(p2.user_id, msg_p2.model_dump_json()),
            return_exceptions=True,
        )
        logger.info(
            "matchmaking.match_created",
            extra={"details": {"match_id": match_id, "p1": p1.user_id, "p2": p2.user_id}},
        )


matchmaking_service = MatchmakingService()