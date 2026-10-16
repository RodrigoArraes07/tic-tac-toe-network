from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.repositories.matches import MatchRecord, MatchRepository
from app.repositories.users import User

router = APIRouter(prefix="/api/matches", tags=["Matches"])


class MatchHistoryItem(BaseModel):
    id: str
    player_x_id: str
    player_o_id: str
    winner_id: str | None
    reason: str
    ended_at: datetime


def get_match_repository(request: Request) -> MatchRepository:
    return request.app.state.match_repository


MatchRepoDep = Annotated[MatchRepository, Depends(get_match_repository)]


def _to_history_item(record: MatchRecord) -> MatchHistoryItem:
    return MatchHistoryItem(
        id=record.id,
        player_x_id=record.player_x_id,
        player_o_id=record.player_o_id,
        winner_id=record.winner_id,
        reason=record.reason,
        ended_at=record.ended_at,
    )


@router.get("/history")
async def get_history(
    current_user: Annotated[User, Depends(get_current_user)],
    match_repo: MatchRepoDep,
) -> list[MatchHistoryItem]:
    """Retorna o histórico das últimas partidas do usuário logado."""
    records = await match_repo.get_user_matches(current_user.id)
    return [_to_history_item(record) for record in records]
