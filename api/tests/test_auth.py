from __future__ import annotations

import time
import uuid

import jwt
import pytest
from fastapi import HTTPException

from app.auth import TokenVerifier, claims_to_user, mint_test_token
from app.config import Settings
from tests.conftest import TEST_JWT_SECRET


def test_valid_hs256_token_yields_user(settings: Settings) -> None:
    user_id = uuid.uuid4()
    token = mint_test_token(TEST_JWT_SECRET, user_id, "a@example.org", aal="aal2")
    user = TokenVerifier(settings).verify(token)
    assert user.id == user_id
    assert user.email == "a@example.org"
    assert user.has_second_factor is True


def test_wrong_secret_is_rejected(settings: Settings) -> None:
    token = mint_test_token("another-secret-another-secret-another-secret-1", uuid.uuid4(), "a@x")
    with pytest.raises(HTTPException) as exc:
        TokenVerifier(settings).verify(token)
    assert exc.value.status_code == 401


def test_expired_token_is_rejected(settings: Settings) -> None:
    payload = {
        "sub": str(uuid.uuid4()),
        "aud": "authenticated",
        "role": "authenticated",
        "exp": int(time.time()) - 10,
    }
    token = jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        TokenVerifier(settings).verify(token)
    assert exc.value.detail == "Session expired"


def test_wrong_audience_is_rejected(settings: Settings) -> None:
    payload = {
        "sub": str(uuid.uuid4()),
        "aud": "something-else",
        "exp": int(time.time()) + 100,
    }
    token = jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")
    with pytest.raises(HTTPException):
        TokenVerifier(settings).verify(token)


def test_alg_none_is_rejected(settings: Settings) -> None:
    payload = {"sub": str(uuid.uuid4()), "aud": "authenticated", "exp": int(time.time()) + 100}
    token = jwt.encode(payload, key="", algorithm="none")
    with pytest.raises(HTTPException):
        TokenVerifier(settings).verify(token)


def test_claims_without_valid_sub_rejected() -> None:
    with pytest.raises(HTTPException):
        claims_to_user({"sub": "not-a-uuid"})
