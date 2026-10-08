from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, StrictStr

from app.services.auth import (
    AuthService,
    InvalidCredentialsError,
    InvalidRegistrationError,
    TooManyAttemptsError,
    User,
    UsernameTakenError,
)

INVALID_REGISTRATION_MESSAGE = (
    "Username deve ter de 3 a 20 caracteres (letras, números e _) e a senha de 8 a 72 caracteres."
)
USERNAME_TAKEN_MESSAGE = "Username já existe."
INVALID_CREDENTIALS_MESSAGE = "Usuário ou senha inválidos."
TOO_MANY_ATTEMPTS_MESSAGE = "Muitas tentativas. Tente novamente em instantes."
NOT_AUTHENTICATED_MESSAGE = "Não autenticado."
TOKEN_TYPE = "bearer"
UNKNOWN_IP = "unknown"

router = APIRouter(prefix="/api/auth")
bearer_scheme = HTTPBearer(auto_error=False)


class CredentialsRequest(BaseModel):
    username: StrictStr
    password: StrictStr


class UserResponse(BaseModel):
    id: str
    username: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: UserResponse


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth_service


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
BearerDep = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


async def get_current_user(credentials: BearerDep, auth_service: AuthServiceDep) -> User:
    user = await auth_service.get_user_from_token(credentials.credentials) if credentials else None
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            NOT_AUTHENTICATED_MESSAGE,
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else UNKNOWN_IP


def _to_user_response(user: User) -> UserResponse:
    return UserResponse(id=user.id, username=user.username)


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: CredentialsRequest, request: Request, auth_service: AuthServiceDep
) -> UserResponse:
    try:
        user = await auth_service.register(body.username, body.password, _client_ip(request))
    except InvalidRegistrationError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, INVALID_REGISTRATION_MESSAGE
        ) from exc
    except UsernameTakenError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, USERNAME_TAKEN_MESSAGE) from exc
    return _to_user_response(user)


@router.post("/login")
async def login(
    body: CredentialsRequest, request: Request, auth_service: AuthServiceDep
) -> LoginResponse:
    try:
        result = await auth_service.login(body.username, body.password, _client_ip(request))
    except TooManyAttemptsError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, TOO_MANY_ATTEMPTS_MESSAGE) from exc
    except InvalidCredentialsError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_CREDENTIALS_MESSAGE) from exc
    return LoginResponse(
        access_token=result.access_token,
        token_type=TOKEN_TYPE,
        expires_in=result.expires_in,
        user=_to_user_response(result.user),
    )
