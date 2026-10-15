from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings

JWT_SECRET_MIN_LENGTH = 32


class Settings(BaseSettings):
    mongo_uri: str
    mongo_db: str
    log_level: str = "INFO"
    jwt_secret: SecretStr = Field(min_length=JWT_SECRET_MIN_LENGTH)
    jwt_expires_minutes: int
    invite_timeout_s: int = Field(gt=0)
