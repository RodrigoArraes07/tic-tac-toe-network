import json
import logging
from datetime import UTC, datetime
from typing import Any

import pytest

from app.domain.enums import EndReason, Symbol
from app.services.game_engine import MatchOutcome, PlayerSession
from app.services.game_handlers import MatchFinisher

X_ID = "jogador-x"
O_ID = "jogador-o"


class FakeConnections:
    def __init__(self) -> None:
        self.messages: dict[str, list[dict[str, Any]]] = {X_ID: [], O_ID: []}
        self.statuses: dict[str, str] = {}

    async def send_personal_message(self, user_id: str, message: str) -> None:
        self.messages[user_id].append(json.loads(message))

    def update_status(self, user_id: str, status: str) -> None:
        self.statuses[user_id] = status


class FailingRanking:
    async def record_win(self, winner_id: str, loser_id: str) -> None:
        raise RuntimeError("ranking fora do ar")

    async def record_draw(self, player_a_id: str, player_b_id: str) -> None:
        raise RuntimeError("ranking fora do ar")


class FailingMatchRepository:
    async def create_match_record(self, **fields: Any) -> None:
        raise RuntimeError("banco fora do ar")


def _outcome() -> MatchOutcome:
    now = datetime.now(UTC)
    return MatchOutcome(
        match_id="m1",
        player_x=PlayerSession(user_id=X_ID, username="ana", symbol=Symbol.X),
        player_o=PlayerSession(user_id=O_ID, username="bruno", symbol=Symbol.CIRCLE),
        winner_id=X_ID,
        reason=EndReason.LINE,
        winning_line=[0, 1, 2],
        board=["X", "X", "X", "O", "O", None, None, None, None],
        moves=5,
        started_at=now,
        ended_at=now,
    )


async def test_ranking_and_history_failures_do_not_stop_the_rest(
    caplog: pytest.LogCaptureFixture,
) -> None:
    connections = FakeConnections()
    finisher = MatchFinisher(
        connections,
        FailingRanking(),
        FailingMatchRepository(),
    )

    with caplog.at_level(logging.INFO):
        await finisher.finish(_outcome())

    ended = {
        user_id: [m["payload"]["result"] for m in messages if m["type"] == "MATCH_ENDED"]
        for user_id, messages in connections.messages.items()
    }
    failed_components = [
        getattr(record, "details", {}).get("component")
        for record in caplog.records
        if record.getMessage() == "error.internal"
    ]
    assert ended == {X_ID: ["WIN"], O_ID: ["LOSS"]}
    assert connections.statuses == {X_ID: "FREE", O_ID: "FREE"}
    assert failed_components == ["ranking", "match_history"]
    assert any(record.getMessage() == "match.ended" for record in caplog.records)
