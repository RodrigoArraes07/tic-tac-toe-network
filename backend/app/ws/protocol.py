import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, StrictBool, StrictInt, StrictStr

from app.domain.enums import Symbol


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


class MovePayload(BaseModel):
    match_id: StrictStr
    cell: StrictInt
    seq: StrictInt


class ForfeitPayload(BaseModel):
    match_id: StrictStr


class MatchSyncPayload(BaseModel):
    match_id: StrictStr


class InviteSendPayload(BaseModel):
    to_username: StrictStr


class InviteRespondPayload(BaseModel):
    match_id: StrictStr
    accept: StrictBool


class InviteCancelPayload(BaseModel):
    match_id: StrictStr
