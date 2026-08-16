"""Shared FastAPI dependencies: DB session + current-user resolution.

Assumes `app.db.session` exposes a `SessionLocal` sessionmaker -- reasonable
given it already defines `Base` (see `from app.db.session import Base` in
models.py). If your session factory has a different name or lives elsewhere,
only `get_db` below needs to change; nothing else in the app depends on it
directly.
"""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.models import User
from app.db.session import SessionLocal

# tokenUrl is just what shows up in the OpenAPI "Authorize" dialog -- point
# it at wherever your login endpoint actually lives.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),  # noqa: B008 — standard FastAPI dependency injection pattern
) -> User:
    # decode_access_token already raises HTTPException(401) for a bad,
    # expired, or wrong-type token -- nothing to catch here.
    user_id = decode_access_token(token)

    user = db.get(User, user_id)
    if user is None or user.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User account is inactive")

    return user
