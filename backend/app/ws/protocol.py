import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain.enums import EndReason, MatchResultType, Symbol


class WSMessageEnvelope(BaseModel):
    type: str
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ref: str | None = None
    ts: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    payload: dict[str, Any] = Field(default_factory=dict)


class AuthPayload(BaseModel):
    token: str


class OpponentInfo(BaseModel):
    id: str
    username: str


class MatchFoundPayload(BaseModel):
    match_id: str
    symbol: Symbol
    opponent: OpponentInfo


class MakeMovePayload(BaseModel):
    cell: int = Field(ge=0, le=8)


class GameStatePayload(BaseModel):
    match_id: str
    board: list[Symbol | None]
    current_turn: Symbol
    turn_expires_at: str


class GameOverPayload(BaseModel):
    match_id: str
    winner_id: str | None
    reason: EndReason
    result_type: MatchResultType
