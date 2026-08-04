"""Password and JWT primitives used by the authentication boundary."""

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
from fastapi import HTTPException, status
from pwdlib import PasswordHash

from app.core.config import settings

password_hash = PasswordHash.recommended()


@dataclass(frozen=True)
class RefreshTokenPayload:
    token: str
    jti: str
    expires_at: datetime


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def hash_refresh_token(token: str) -> str:
    """Produce a keyed digest so a database leak does not expose sessions."""
    return hmac.new(settings.jwt_secret.encode(), token.encode(), hashlib.sha256).hexdigest()


def _create_token(subject: UUID, token_type: str, expires_at: datetime, jti: str) -> str:
    return jwt.encode(
        {"sub": str(subject), "typ": token_type, "jti": jti, "iat": datetime.now(timezone.utc), "exp": expires_at},
        settings.jwt_secret,
        algorithm="HS256",
    )


def create_access_token(subject: UUID) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return _create_token(subject, "access", expires_at, str(uuid4()))


def create_refresh_token(subject: UUID) -> RefreshTokenPayload:
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    jti = str(uuid4())
    return RefreshTokenPayload(_create_token(subject, "refresh", expires_at, jti), jti, expires_at)

def _decode_token(token: str, expected_type: str) -> dict[str, str]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        if payload.get("typ") != expected_type or not payload.get("jti"):
            raise ValueError("Unexpected token type")
        UUID(payload["sub"])
        return payload
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError) as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid or expired {expected_type} token") from error


def decode_access_token(token: str) -> UUID:
    return UUID(_decode_token(token, "access")["sub"])


def decode_refresh_token(token: str) -> dict[str, str]:
    return _decode_token(token, "refresh")
