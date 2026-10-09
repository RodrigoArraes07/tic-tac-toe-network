from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

JWT_ALGORITHM = "HS256"
REQUIRED_CLAIMS = ["sub", "username", "iat", "exp"]

_hasher = PasswordHasher()


class InvalidTokenError(Exception):
    pass


@dataclass(frozen=True)
class TokenClaims:
    user_id: str
    username: str


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerificationError, InvalidHashError:
        return False


def create_access_token(user_id: str, username: str, secret: str, expires_minutes: int) -> str:
    issued_at = datetime.now(UTC)
    claims = {
        "sub": user_id,
        "username": username,
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(claims, secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, secret: str) -> TokenClaims:
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": REQUIRED_CLAIMS},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError from exc
    username = claims["username"]
    if not isinstance(username, str):
        raise InvalidTokenError
    return TokenClaims(user_id=claims["sub"], username=username)
