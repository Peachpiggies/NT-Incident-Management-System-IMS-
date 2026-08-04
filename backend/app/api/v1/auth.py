import hmac
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user
from app.core.security import create_access_token, create_refresh_token, decode_refresh_token, hash_password, hash_refresh_token, verify_password
from app.db.models import ActivityLog, LoginHistory, RefreshToken, Role, User, UserRole
from app.db.session import get_db

router = APIRouter(tags=["Auth"])


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserRegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    full_name: str = Field(..., min_length=3, max_length=200)
    username: str | None = Field(None, min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9._-]+$")
    password: str = Field(..., min_length=12, max_length=128)


class UserLoginRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=12, max_length=128)


async def _get_user_by_email(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(select(User).where(User.email == email.lower()))


async def _get_user_by_id(db: AsyncSession, user_id: UUID) -> User | None:
    return await db.get(User, user_id)


async def _issue_tokens(db: AsyncSession, user: User) -> AuthResponse:
    refresh = create_refresh_token(user.id)
    entity = RefreshToken(user_id=user.id, token_hash=hash_refresh_token(refresh.token), jti=refresh.jti, expires_at=refresh.expires_at)
    db.add(entity)
    await db.flush()
    return AuthResponse(access_token=create_access_token(user.id), refresh_token=refresh.token)


async def _revoke_all_refresh_tokens(db: AsyncSession, user_id: UUID) -> None:
    await db.execute(update(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)).values(revoked_at=datetime.now(timezone.utc)))


def _is_expired(expires_at: datetime) -> bool:
    # SQLite omits timezone info in test databases; PostgreSQL returns it.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= datetime.now(timezone.utc)


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(request: UserRegisterRequest, db: Annotated[AsyncSession, Depends(get_db)]) -> AuthResponse:
    email = request.email.lower()
    username = request.username or email.split("@", 1)[0]
    if await _get_user_by_email(db, email) or await db.scalar(select(User).where(User.username == username)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email or username already registered")
    names = request.full_name.strip().split(maxsplit=1)
    user = User(username=username, email=email, first_name=names[0], last_name=names[1] if len(names) > 1 else "-", password_hash=hash_password(request.password))
    db.add(user)
    await db.flush()
    customer = await db.scalar(select(Role).where(Role.code == "customer", Role.is_deleted.is_(False)))
    if not customer:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Role seed data is unavailable")
    db.add(UserRole(user_id=user.id, role_id=customer.id, created_by=user.id))
    db.add(ActivityLog(user_id=user.id, module="auth", action="register", resource="user", resource_id=user.id))
    response = await _issue_tokens(db, user)
    await db.commit()
    return response


@router.post("/login", response_model=AuthResponse)
async def login(request: UserLoginRequest, db: Annotated[AsyncSession, Depends(get_db)]) -> AuthResponse:
    user = await _get_user_by_email(db, request.email)
    if not user or not user.is_active or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    user.last_login = datetime.now(timezone.utc)
    db.add(LoginHistory(user_id=user.id))
    db.add(ActivityLog(user_id=user.id, module="auth", action="login", resource="user", resource_id=user.id))
    response = await _issue_tokens(db, user)
    await db.commit()
    return response


@router.post("/refresh", response_model=AuthResponse)
async def refresh(request: RefreshRequest, db: Annotated[AsyncSession, Depends(get_db)]) -> AuthResponse:
    payload = decode_refresh_token(request.refresh_token)
    entity = await db.scalar(select(RefreshToken).where(RefreshToken.jti == payload["jti"]).with_for_update())
    if not entity or entity.user_id != UUID(payload["sub"]) or not hmac.compare_digest(entity.token_hash, hash_refresh_token(request.refresh_token)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    if entity.revoked_at is not None:
        await _revoke_all_refresh_tokens(db, entity.user_id)
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token reuse detected; all sessions were revoked")
    if _is_expired(entity.expires_at):
        entity.revoked_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    user = await _get_user_by_id(db, entity.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    entity.revoked_at = datetime.now(timezone.utc)
    response = await _issue_tokens(db, user)
    replacement = await db.scalar(select(RefreshToken).where(RefreshToken.jti == decode_refresh_token(response.refresh_token)["jti"]))
    entity.replaced_by_id = replacement.id
    await db.commit()
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: RefreshRequest, db: Annotated[AsyncSession, Depends(get_db)]) -> None:
    payload = decode_refresh_token(request.refresh_token)
    entity = await db.scalar(select(RefreshToken).where(RefreshToken.jti == payload["jti"]))
    if entity and hmac.compare_digest(entity.token_hash, hash_refresh_token(request.refresh_token)) and entity.revoked_at is None:
        entity.revoked_at = datetime.now(timezone.utc)
        await db.commit()


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(request: ChangePasswordRequest, current_user: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]) -> None:
    if not verify_password(request.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    if verify_password(request.new_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must differ from the current password")
    current_user.password_hash = hash_password(request.new_password)
    await _revoke_all_refresh_tokens(db, current_user.id)
    db.add(ActivityLog(user_id=current_user.id, module="auth", action="change_password", resource="user", resource_id=current_user.id))
    await db.commit()
