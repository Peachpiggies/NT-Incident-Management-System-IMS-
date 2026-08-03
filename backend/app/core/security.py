from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, status
from pwdlib import PasswordHash

from app.core.config import settings

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def create_access_token(subject: int) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({"sub": str(subject), "exp": expires}, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> int:
    try:
        return int(jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from error


# --- Refresh token helpers ---
DEFAULT_REFRESH_DAYS = 7


def create_refresh_token(subject: int, days: int | None = None) -> str:
    """
    Create a refresh token for `subject`. Uses settings.jwt_secret and a longer expiry.
    If `days` is provided it overrides the default expiry days.
    """
    expire_days = days if days is not None else DEFAULT_REFRESH_DAYS
    expires = datetime.now(timezone.utc) + timedelta(days=expire_days)
    return jwt.encode({"sub": str(subject), "exp": expires}, settings.jwt_secret, algorithm="HS256")


def decode_refresh_token(token: str) -> int:
    """
    Decode a refresh token and return the subject as int. Raises HTTPException on failure.
    """
    try:
        return int(jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token") from error
