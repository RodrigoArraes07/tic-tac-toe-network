import asyncio
import logging
import re
import secrets
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core import security
from app.repositories.users import DuplicateUsernameError, User, UserRepository

USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 20
USERNAME_PATTERN = re.compile(rf"[a-zA-Z0-9_]{{{USERNAME_MIN_LENGTH},{USERNAME_MAX_LENGTH}}}")
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 72
MAX_FAILED_LOGINS = 5
FAILED_LOGIN_WINDOW_SECONDS = 60
SECONDS_PER_MINUTE = 60

logger = logging.getLogger(__name__)

type AttemptKey = tuple[str, str]


class InvalidRegistrationError(Exception):
    pass


class UsernameTakenError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class TooManyAttemptsError(Exception):
    pass


@dataclass(frozen=True)
class LoginResult:
    access_token: str
    expires_in: int
    user: User


class LoginAttemptLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._failures: dict[AttemptKey, deque[float]] = {}

    def is_blocked(self, key: AttemptKey) -> bool:
        failures = self._failures.get(key)
        if failures is None:
            return False
        window_start = self._clock() - FAILED_LOGIN_WINDOW_SECONDS
        while failures and failures[0] <= window_start:
            failures.popleft()
        if not failures:
            del self._failures[key]
            return False
        return len(failures) >= MAX_FAILED_LOGINS

    def register_failure(self, key: AttemptKey) -> None:
        self._failures.setdefault(key, deque()).append(self._clock())

    def reset(self, key: AttemptKey) -> None:
        self._failures.pop(key, None)


def _is_valid_username(username: str) -> bool:
    return USERNAME_PATTERN.fullmatch(username) is not None


def _is_valid_password(password: str) -> bool:
    return PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH


class AuthService:
    def __init__(
        self,
        users: UserRepository,
        jwt_secret: str,
        jwt_expires_minutes: int,
        limiter: LoginAttemptLimiter | None = None,
    ) -> None:
        self._users = users
        self._jwt_secret = jwt_secret
        self._jwt_expires_minutes = jwt_expires_minutes
        self._limiter = limiter or LoginAttemptLimiter()
        # Verificado quando o usuário não existe, para o tempo de resposta
        # não revelar quais usernames estão cadastrados.
        self._placeholder_hash = security.hash_password(secrets.token_urlsafe())

    async def register(self, username: str, password: str, ip: str) -> User:
        if not (_is_valid_username(username) and _is_valid_password(password)):
            raise InvalidRegistrationError
        password_hash = await asyncio.to_thread(security.hash_password, password)
        try:
            user = await self._users.insert(username, password_hash, datetime.now(UTC))
        except DuplicateUsernameError as exc:
            raise UsernameTakenError from exc
        details = {"user_id": user.id, "username": user.username, "ip": ip}
        logger.info("user.registered", extra={"details": details})
        return user

    async def login(self, username: str, password: str, ip: str) -> LoginResult:
        attempted_username = username.lower()[:USERNAME_MAX_LENGTH]
        key = (attempted_username, ip)
        if self._limiter.is_blocked(key):
            logger.warning(
                "security.rate_limited", extra={"details": {"ip": ip, "reason": "login"}}
            )
            raise TooManyAttemptsError
        user, password_ok = await self._authenticate(username, password)
        if user is None or not password_ok:
            self._limiter.register_failure(key)
            details = {
                "user_id": user.id if user else None,
                "username": attempted_username,
                "ip": ip,
            }
            logger.warning("user.login_failed", extra={"details": details})
            raise InvalidCredentialsError
        self._limiter.reset(key)
        await self._users.update_last_login(user.id, datetime.now(UTC))
        details = {"user_id": user.id, "username": user.username, "ip": ip}
        logger.info("user.login", extra={"details": details})
        return self._issue_token(user)

    async def get_user_from_token(self, token: str) -> User | None:
        try:
            claims = security.decode_access_token(token, self._jwt_secret)
        except security.InvalidTokenError:
            return None
        return await self._users.find_by_id(claims.user_id)

    async def _authenticate(self, username: str, password: str) -> tuple[User | None, bool]:
        """Devolve o usuário encontrado (ou None) e se a senha confere."""
        if not (_is_valid_username(username) and _is_valid_password(password)):
            return None, False
        user = await self._users.find_by_username(username)
        password_hash = user.password_hash if user else self._placeholder_hash
        matches = await asyncio.to_thread(security.verify_password, password_hash, password)
        return user, matches and user is not None

    def _issue_token(self, user: User) -> LoginResult:
        token = security.create_access_token(
            user.id, user.username, self._jwt_secret, self._jwt_expires_minutes
        )
        return LoginResult(
            access_token=token,
            expires_in=self._jwt_expires_minutes * SECONDS_PER_MINUTE,
            user=user,
        )
