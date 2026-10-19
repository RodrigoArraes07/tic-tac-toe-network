from dataclasses import dataclass

from app.repositories.users import UserRepository

DEFAULT_RANKING_LIMIT = 20
MIN_RANKING_LIMIT = 1
MAX_RANKING_LIMIT = 100
FIRST_POSITION = 1


@dataclass(frozen=True)
class RankingEntry:
    position: int
    username: str
    points: int
    wins: int
    draws: int
    losses: int


def _require_distinct_players(first_id: str, second_id: str) -> None:
    if first_id == second_id:
        raise ValueError("a partida precisa de dois jogadores diferentes")


class RankingService:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def get_ranking(self, limit: int = DEFAULT_RANKING_LIMIT) -> list[RankingEntry]:
        scores = await self._users.list_ranking(limit)
        return [
            RankingEntry(
                position=position,
                username=score.username,
                points=score.stats.points,
                wins=score.stats.wins,
                draws=score.stats.draws,
                losses=score.stats.losses,
            )
            for position, score in enumerate(scores, start=FIRST_POSITION)
        ]

    async def record_win(self, winner_id: str, loser_id: str) -> None:
        _require_distinct_players(winner_id, loser_id)
        await self._users.apply_win(winner_id, loser_id)

    async def record_draw(self, player_a_id: str, player_b_id: str) -> None:
        _require_distinct_players(player_a_id, player_b_id)
        await self._users.apply_draw(player_a_id, player_b_id)
