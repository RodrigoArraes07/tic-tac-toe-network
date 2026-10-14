from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class MatchRecord(BaseModel):
    id: str = Field(alias="_id")
    player_x_id: str
    player_o_id: str
    winner_id: str | None
    reason: str
    ended_at: datetime


class MatchRepository:
    def __init__(self, db: Any) -> None:
        self._collection = db["matches"]

    async def create_match_record(
        self,
        match_id: str,
        player_x_id: str,
        player_o_id: str,
        winner_id: str | None,
        reason: str,
    ) -> MatchRecord:
        record = {
            "_id": match_id,
            "player_x_id": player_x_id,
            "player_o_id": player_o_id,
            "winner_id": winner_id,
            "reason": reason,
            "ended_at": datetime.now(UTC),
        }
        await self._collection.insert_one(record)
        return MatchRecord(**record)

    async def get_user_matches(self, user_id: str, limit: int = 20) -> list[MatchRecord]:
        cursor = (
            self._collection.find(
                {"$or": [{"player_x_id": user_id}, {"player_o_id": user_id}]}
            )
            .sort("ended_at", -1)
            .limit(limit)
        )

        records = []
        async for doc in cursor:
            records.append(MatchRecord(**doc))
        return records