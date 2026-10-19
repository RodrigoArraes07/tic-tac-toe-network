from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.services.ranking import (
    DEFAULT_RANKING_LIMIT,
    MAX_RANKING_LIMIT,
    MIN_RANKING_LIMIT,
    RankingService,
)

router = APIRouter(prefix="/api")


class RankingEntryResponse(BaseModel):
    position: int
    username: str
    points: int
    wins: int
    draws: int
    losses: int


def get_ranking_service(request: Request) -> RankingService:
    return request.app.state.ranking_service


RankingServiceDep = Annotated[RankingService, Depends(get_ranking_service)]
LimitQuery = Annotated[int, Query(ge=MIN_RANKING_LIMIT, le=MAX_RANKING_LIMIT)]


@router.get("/ranking", dependencies=[Depends(get_current_user)])
async def ranking(
    ranking_service: RankingServiceDep, limit: LimitQuery = DEFAULT_RANKING_LIMIT
) -> list[RankingEntryResponse]:
    entries = await ranking_service.get_ranking(limit)
    return [
        RankingEntryResponse(
            position=entry.position,
            username=entry.username,
            points=entry.points,
            wins=entry.wins,
            draws=entry.draws,
            losses=entry.losses,
        )
        for entry in entries
    ]
