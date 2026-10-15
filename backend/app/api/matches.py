from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.auth import get_current_user
from app.repositories.matches import MatchRecord, MatchRepository
from app.repositories.users import User

router = APIRouter(prefix="/api/matches", tags=["Matches"])


def get_match_repository(request: Request) -> MatchRepository:
    return request.app.state.match_repository


MatchRepoDep = Annotated[MatchRepository, Depends(get_match_repository)]


@router.get("/history")
async def get_history(
    current_user: Annotated[User, Depends(get_current_user)],
    match_repo: MatchRepoDep,
) -> list[MatchRecord]:
    """Retorna o histórico das últimas partidas do usuário logado."""
    return await match_repo.get_user_matches(current_user.id)
