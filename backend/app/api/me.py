from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.services.auth import User

router = APIRouter(prefix="/api")


class StatsResponse(BaseModel):
    wins: int
    losses: int
    draws: int
    points: int


class MeResponse(BaseModel):
    id: str
    username: str
    stats: StatsResponse


@router.get("/me")
async def me(user: Annotated[User, Depends(get_current_user)]) -> MeResponse:
    stats = StatsResponse(
        wins=user.stats.wins,
        losses=user.stats.losses,
        draws=user.stats.draws,
        points=user.stats.points,
    )
    return MeResponse(id=user.id, username=user.username, stats=stats)
