from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.db.models import RefreshToken, User
from app.db.session import get_db

router = APIRouter(tags=["Auth"])


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserRegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=3)
    password: str = Field(..., min_length=8)


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)


class RefreshRequest(BaseModel):
    refresh_token: str


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(request: UserRegisterRequest, db: Annotated[AsyncSession, Depends(get_db)]) -> AuthResponse:
    existing_user = await get_user_by_email(db, request.email)
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user = User(
        email=request.email,
        full_name=request.full_name,
        password_hash=hash_password(request.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    token = RefreshToken(
        user_id=user.id,
        token=refresh_token,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(token)
    await db.commit()

    return AuthResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=AuthResponse)
async def login(request: UserLoginRequest, db: Annotated[AsyncSession, Depends(get_db)]) -> AuthResponse:
    user = await get_user_by_email(db, request.email)
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    token = RefreshToken(
        user_id=user.id,
        token=refresh_token,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(token)
    await db.commit()

    return AuthResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=AuthResponse)
async def refresh(request: RefreshRequest, db: Annotated[AsyncSession, Depends(get_db)]) -> AuthResponse:
    user_id = decode_refresh_token(request.refresh_token)
    db_refresh = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token == request.refresh_token,
            not RefreshToken.revoked,
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
    )
    refresh_token_entity = db_refresh.scalar_one_or_none()
    if not refresh_token_entity:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    refresh_token_entity.revoked = True
    await db.commit()

    access_token = create_access_token(user.id)
    new_refresh_token = create_refresh_token(user.id)

    token = RefreshToken(
        user_id=user.id,
        token=new_refresh_token,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(token)
    await db.commit()

    return AuthResponse(access_token=access_token, refresh_token=new_refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: RefreshRequest, db: Annotated[AsyncSession, Depends(get_db)]) -> None:
    db_refresh = await db.execute(select(RefreshToken).where(RefreshToken.token == request.refresh_token))
    refresh_token_entity = db_refresh.scalar_one_or_none()
    if refresh_token_entity:
        refresh_token_entity.revoked = True
        await db.commit()
