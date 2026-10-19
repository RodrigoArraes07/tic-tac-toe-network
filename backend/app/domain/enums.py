from enum import StrEnum


class Symbol(StrEnum):
    X = "X"
    CIRCLE = "O"


class MatchStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    FINISHED = "FINISHED"


class EndReason(StrEnum):
    LINE = "LINE"
    DRAW = "DRAW"
    FORFEIT = "FORFEIT"
    DISCONNECT = "DISCONNECT"
    TIMEOUT = "TIMEOUT"


class MatchResultType(StrEnum):
    WIN = "WIN"
    LOSS = "LOSS"
    DRAW = "DRAW"
