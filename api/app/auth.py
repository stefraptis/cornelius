"""Authentication: verify Supabase Auth JWTs.

The browser signs in with Supabase Auth and sends the access token as a Bearer
header. The API verifies the token locally, with either the project's legacy
HS256 secret or the project's JWKS (asymmetric keys), and never calls Supabase
for every request.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.config import Settings, get_settings

log = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthUser:
    id: uuid.UUID
    email: str | None
    role: str = "authenticated"
    aal: str = "aal1"  # aal2 after a second factor
    claims: dict[str, Any] | None = None

    @property
    def has_second_factor(self) -> bool:
        return self.aal == "aal2"


class TokenVerifier:
    """Verifies tokens for one Supabase project.

    Supabase signs access tokens either with the project's legacy shared
    secret (HS256) or, after the project switches to JWT signing keys, with an
    asymmetric key published at /auth/v1/.well-known/jwks.json (ES256 or
    RS256). The token header says which; both are supported, and a token of a
    kind the API is not configured for produces a message that says what to
    configure instead of a bare "invalid token".
    """

    ASYMMETRIC = ("ES256", "RS256")

    def __init__(self, settings: Settings):
        self._settings = settings
        jwks_url = settings.supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"
        self._jwks = PyJWKClient(
            jwks_url,
            cache_keys=True,
            lifespan=3600,
            headers={"User-Agent": f"{settings.app_name}-api/0.1"},
        )

    def verify(self, token: str) -> AuthUser:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from exc
        alg = str(header.get("alg", ""))

        try:
            if alg == "HS256":
                if not self._settings.supabase_jwt_secret:
                    log.warning("auth.hs256_token_without_secret")
                    raise HTTPException(
                        status.HTTP_401_UNAUTHORIZED,
                        "This Supabase project signs tokens with the legacy HS256 secret. "
                        "Set SUPABASE_JWT_SECRET in the API environment, or switch the "
                        "project to JWT signing keys (Project Settings > JWT Keys).",
                    )
                claims = jwt.decode(
                    token,
                    self._settings.supabase_jwt_secret,
                    algorithms=["HS256"],
                    audience="authenticated",
                    options={"require": ["exp", "sub"]},
                )
            elif alg in self.ASYMMETRIC:
                signing_key = self._jwks.get_signing_key_from_jwt(token)
                claims = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=list(self.ASYMMETRIC),
                    audience="authenticated",
                    options={"require": ["exp", "sub"]},
                )
            else:
                raise HTTPException(
                    status.HTTP_401_UNAUTHORIZED, f"Unsupported token algorithm {alg}"
                )
        except jwt.ExpiredSignatureError as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired") from exc
        except jwt.PyJWTError as exc:
            # The reason is logged server side; in development it is also returned.
            log.warning("auth.invalid_token", extra={"ctx_alg": alg, "ctx_reason": str(exc)})
            detail = "Invalid token"
            if not self._settings.is_production:
                detail = f"Invalid token: {exc}"
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail) from exc

        return claims_to_user(claims)


def claims_to_user(claims: dict[str, Any]) -> AuthUser:
    try:
        user_id = uuid.UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token subject") from exc
    return AuthUser(
        id=user_id,
        email=claims.get("email"),
        role=str(claims.get("role", "authenticated")),
        aal=str(claims.get("aal", "aal1")),
        claims=claims,
    )


_verifier: TokenVerifier | None = None


def get_verifier(settings: Settings = Depends(get_settings)) -> TokenVerifier:
    global _verifier
    if _verifier is None or _verifier._settings is not settings:
        _verifier = TokenVerifier(settings)
    return _verifier


def reset_verifier() -> None:
    global _verifier
    _verifier = None


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    verifier: TokenVerifier = Depends(get_verifier),
) -> AuthUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Sign in to continue",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = verifier.verify(credentials.credentials)
    request.state.user = user
    return user


def require_second_factor(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    """For admin actions: the session must have completed a second factor."""
    if not user.has_second_factor:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Two-factor authentication required")
    return user


def mint_test_token(secret: str, user_id: uuid.UUID, email: str, aal: str = "aal1") -> str:
    """Create an HS256 token shaped like Supabase's, for tests only."""
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": "authenticated",
        "aud": "authenticated",
        "aal": aal,
        "iat": now,
        "exp": now + 3600,
        "iss": "test",
    }
    return jwt.encode(payload, secret, algorithm="HS256")
