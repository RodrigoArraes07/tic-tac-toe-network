from typing import Annotated, Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode

JWT_SECRET_MIN_LENGTH = 32
DEFAULT_ALLOWED_ORIGINS = ["http://localhost:5173", "https://localhost"]
ORIGIN_SEPARATOR = ","


def normalize_origin(origin: str) -> str:
    return origin.strip().rstrip("/").lower()


class Settings(BaseSettings):
    mongo_uri: str
    mongo_db: str
    log_level: str = "INFO"
    jwt_secret: SecretStr = Field(min_length=JWT_SECRET_MIN_LENGTH)
    jwt_expires_minutes: int
    invite_timeout_s: int = Field(gt=0)
    audit_enabled: bool = True
    ws_rate_per_second: float = Field(default=10, gt=0)
    ws_rate_burst: int = Field(default=20, gt=0)
    ws_max_message_bytes: int = Field(default=4096, gt=0)
    # NoDecode: o valor do ambiente é uma lista separada por vírgula, não JSON.
    allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: list(DEFAULT_ALLOWED_ORIGINS)
    )

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: Any) -> Any:
        items = value.split(ORIGIN_SEPARATOR) if isinstance(value, str) else value
        if not isinstance(items, list):
            return items
        return [normalize_origin(item) for item in items if str(item).strip()]
