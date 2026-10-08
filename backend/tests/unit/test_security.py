import jwt
import pytest

from app.core.security import (
    JWT_ALGORITHM,
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

SECRET = "segredo-usado-apenas-nos-testes-de-seguranca"
OTHER_SECRET = "outro-segredo-usado-apenas-nos-testes-unitarios"
PASSWORD = "senha-correta-123"
USER_ID = "6710a1b2c3d4e5f601234567"
USERNAME = "alice"
EXPIRES_MINUTES = 60


def test_hash_password_uses_argon2id_and_hides_the_password() -> None:
    password_hash = hash_password(PASSWORD)

    assert password_hash.startswith("$argon2id$")
    assert PASSWORD not in password_hash


def test_hash_password_uses_a_different_salt_each_time() -> None:
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_verify_password_accepts_the_right_password() -> None:
    assert verify_password(hash_password(PASSWORD), PASSWORD) is True


def test_verify_password_rejects_a_wrong_password() -> None:
    assert verify_password(hash_password(PASSWORD), "senha-errada-123") is False


def test_verify_password_rejects_a_malformed_hash() -> None:
    assert verify_password("nao-e-um-hash", PASSWORD) is False


def test_access_token_carries_the_expected_claims() -> None:
    token = create_access_token(USER_ID, USERNAME, SECRET, EXPIRES_MINUTES)

    claims = jwt.decode(token, SECRET, algorithms=[JWT_ALGORITHM])

    assert claims["sub"] == USER_ID
    assert claims["username"] == USERNAME
    assert claims["exp"] - claims["iat"] == EXPIRES_MINUTES * 60
    assert jwt.get_unverified_header(token)["alg"] == JWT_ALGORITHM


def test_decode_access_token_returns_the_user_identity() -> None:
    token = create_access_token(USER_ID, USERNAME, SECRET, EXPIRES_MINUTES)

    claims = decode_access_token(token, SECRET)

    assert claims.user_id == USER_ID
    assert claims.username == USERNAME


def test_decode_access_token_rejects_an_expired_token() -> None:
    token = create_access_token(USER_ID, USERNAME, SECRET, expires_minutes=-1)

    with pytest.raises(InvalidTokenError):
        decode_access_token(token, SECRET)


def test_decode_access_token_rejects_another_secret() -> None:
    token = create_access_token(USER_ID, USERNAME, SECRET, EXPIRES_MINUTES)

    with pytest.raises(InvalidTokenError):
        decode_access_token(token, OTHER_SECRET)


def test_decode_access_token_rejects_a_tampered_token() -> None:
    token = create_access_token(USER_ID, USERNAME, SECRET, EXPIRES_MINUTES)
    header, payload, signature = token.split(".")
    forged_payload = jwt.utils.base64url_encode(b'{"sub":"outro","username":"admin"}').decode()

    with pytest.raises(InvalidTokenError):
        decode_access_token(f"{header}.{forged_payload}.{signature}", SECRET)


def test_decode_access_token_rejects_a_token_without_required_claims() -> None:
    token = jwt.encode({"sub": USER_ID}, SECRET, algorithm=JWT_ALGORITHM)

    with pytest.raises(InvalidTokenError):
        decode_access_token(token, SECRET)


def test_decode_access_token_rejects_an_unsigned_token() -> None:
    token = jwt.encode({"sub": USER_ID, "username": USERNAME}, None, algorithm="none")

    with pytest.raises(InvalidTokenError):
        decode_access_token(token, SECRET)
