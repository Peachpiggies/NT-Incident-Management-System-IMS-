import hmac
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.core.validation import normalize_email, validate_password
from app.db.models import (
    ActivityLog,
    LoginHistory,
    RefreshToken,
    Role,
    User,
    UserRole,
)
from app.db.session import get_db

router = APIRouter(tags=["Auth"])


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserRegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    full_name: str = Field(..., min_length=3, max_length=200)
    username: str | None = Field(
        None, min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9._-]+$"
    )
    password: str = Field(..., min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return validate_password(value)


class UserLoginRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return validate_password(value)


class SessionResponse(BaseModel):
    session_id: UUID
    ip: str | None
    device: str | None
    browser: str | None
    user_agent: str | None
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime

    model_config = ConfigDict(from_attributes=True)


async def _get_user_by_email(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(select(User).where(User.email == email.lower()))


async def _get_user_by_id(db: AsyncSession, user_id: UUID) -> User | None:
    return await db.get(User, user_id)


def _request_metadata(request: Request | None) -> dict[str, str | None]:
    if request is None:
        return {"ip": None, "device": None, "browser": None, "user_agent": None}
    user_agent = request.headers.get("user-agent")
    return {
        "ip": request.client.host if request.client else None,
        "device": request.headers.get("x-device-name", user_agent)[:255]
        if request.headers.get("x-device-name", user_agent)
        else None,
        "browser": request.headers.get("sec-ch-ua", user_agent)[:255]
        if request.headers.get("sec-ch-ua", user_agent)
        else None,
        "user_agent": user_agent[:500] if user_agent else None,
    }


async def _issue_tokens(
    db: AsyncSession,
    user: User,
    metadata: dict[str, str | None],
    *,
    session_id: UUID | None = None,
    login_history_id: UUID | None = None,
) -> AuthResponse:
    refresh = create_refresh_token(user.id)
    entity = RefreshToken(
        session_id=session_id or uuid4(),
        user_id=user.id,
        login_history_id=login_history_id,
        token_hash=hash_refresh_token(refresh.token),
        jti=refresh.jti,
        expires_at=refresh.expires_at,
        **metadata,
    )
    db.add(entity)
    await db.flush()
    return AuthResponse(
        access_token=create_access_token(user.id), refresh_token=refresh.token
    )


async def _revoke_all_refresh_tokens(db: AsyncSession, user_id: UUID) -> None:
    tokens = list(
        (
            await db.scalars(
                select(RefreshToken).where(
                    RefreshToken.user_id == user_id,
                    RefreshToken.revoked_at.is_(None),
                )
            )
        ).all()
    )
    await _revoke_tokens(db, tokens)


async def _revoke_tokens(db: AsyncSession, tokens: list[RefreshToken]) -> None:
    now = datetime.now(timezone.utc)
    login_history_ids = {
        token.login_history_id for token in tokens if token.login_history_id
    }
    for token in tokens:
        token.revoked_at = now
    for history_id in login_history_ids:
        history = await db.get(LoginHistory, history_id)
        if history and history.logout_at is None:
            history.logout_at = now


def _is_expired(expires_at: datetime) -> bool:
    # SQLite omits timezone info in test databases; PostgreSQL returns it.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= datetime.now(timezone.utc)


@router.post(
    "/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED
)
async def register(
    request: UserRegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    http_request: Request = None,
) -> AuthResponse:
    email = request.email.lower()
    username = request.username or email.split("@", 1)[0]
    if await _get_user_by_email(db, email) or await db.scalar(
        select(User).where(User.username == username)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email or username already registered",
        )
    names = request.full_name.strip().split(maxsplit=1)
    user = User(
        username=username,
        email=email,
        first_name=names[0],
        last_name=names[1] if len(names) > 1 else "-",
        password_hash=hash_password(request.password),
    )
    db.add(user)
    await db.flush()
    customer = await db.scalar(
        select(Role).where(Role.code == "customer", Role.is_deleted.is_(False))
    )
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Role seed data is unavailable",
        )
    db.add(UserRole(user_id=user.id, role_id=customer.id, created_by=user.id))
    metadata = _request_metadata(http_request)
    db.add(
        ActivityLog(
            user_id=user.id,
            module="auth",
            action="register",
            resource="user",
            resource_id=user.id,
            ip=metadata["ip"],
            user_agent=metadata["user_agent"],
            detail={"device": metadata["device"], "browser": metadata["browser"]},
        )
    )
    login_history = LoginHistory(
        user_id=user.id,
        ip=metadata["ip"],
        device=metadata["device"],
        browser=metadata["browser"],
    )
    db.add(login_history)
    await db.flush()
    response = await _issue_tokens(
        db, user, metadata, login_history_id=login_history.id
    )
    await db.commit()
    return response


@router.post("/login", response_model=AuthResponse)
async def login(
    request: UserLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    http_request: Request = None,
) -> AuthResponse:
    user = await _get_user_by_email(db, request.email)
    if (
        not user
        or not user.is_active
        or not verify_password(request.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    user.last_login = datetime.now(timezone.utc)
    metadata = _request_metadata(http_request)
    login_history = LoginHistory(
        user_id=user.id,
        ip=metadata["ip"],
        device=metadata["device"],
        browser=metadata["browser"],
    )
    db.add(login_history)
    await db.flush()
    db.add(
        ActivityLog(
            user_id=user.id,
            module="auth",
            action="login",
            resource="user",
            resource_id=user.id,
            ip=metadata["ip"],
            user_agent=metadata["user_agent"],
            detail={"device": metadata["device"], "browser": metadata["browser"]},
        )
    )
    response = await _issue_tokens(
        db, user, metadata, login_history_id=login_history.id
    )
    await db.commit()
    return response


@router.post("/refresh", response_model=AuthResponse)
async def refresh(
    request: RefreshRequest, db: Annotated[AsyncSession, Depends(get_db)]
) -> AuthResponse:
    payload = decode_refresh_token(request.refresh_token)
    entity = await db.scalar(
        select(RefreshToken).where(RefreshToken.jti == payload["jti"]).with_for_update()
    )
    if (
        not entity
        or entity.user_id != UUID(payload["sub"])
        or not hmac.compare_digest(
            entity.token_hash, hash_refresh_token(request.refresh_token)
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    if entity.revoked_at is not None:
        await _revoke_all_refresh_tokens(db, entity.user_id)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token reuse detected; all sessions were revoked",
        )
    if _is_expired(entity.expires_at):
        entity.revoked_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    user = await _get_user_by_id(db, entity.user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    entity.last_used_at = datetime.now(timezone.utc)
    entity.revoked_at = datetime.now(timezone.utc)
    response = await _issue_tokens(
        db,
        user,
        {
            "ip": entity.ip,
            "device": entity.device,
            "browser": entity.browser,
            "user_agent": entity.user_agent,
        },
        session_id=entity.session_id,
        login_history_id=entity.login_history_id,
    )
    replacement = await db.scalar(
        select(RefreshToken).where(
            RefreshToken.jti == decode_refresh_token(response.refresh_token)["jti"]
        )
    )
    entity.replaced_by_id = replacement.id
    await db.commit()
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    http_request: Request = None,
) -> None:
    payload = decode_refresh_token(request.refresh_token)
    entity = await db.scalar(
        select(RefreshToken).where(RefreshToken.jti == payload["jti"])
    )
    if (
        entity
        and hmac.compare_digest(
            entity.token_hash, hash_refresh_token(request.refresh_token)
        )
        and entity.revoked_at is None
    ):
        await _revoke_tokens(db, [entity])
        metadata = _request_metadata(http_request)
        db.add(
            ActivityLog(
                user_id=entity.user_id,
                module="auth",
                action="logout",
                resource="session",
                resource_id=entity.session_id,
                ip=metadata["ip"],
                user_agent=metadata["user_agent"],
                detail={"device": metadata["device"], "browser": metadata["browser"]},
            )
        )
        await db.commit()


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[RefreshToken]:
    """Return active logical sessions; token hashes and JTIs are never exposed."""
    now = datetime.now(timezone.utc)
    return list(
        (
            await db.scalars(
                select(RefreshToken)
                .where(
                    RefreshToken.user_id == current_user.id,
                    RefreshToken.revoked_at.is_(None),
                    RefreshToken.expires_at > now,
                )
                .order_by(RefreshToken.last_used_at.desc())
            )
        ).all()
    )


@router.post("/sessions/{session_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    tokens = list(
        (
            await db.scalars(
                select(RefreshToken).where(
                    RefreshToken.user_id == current_user.id,
                    RefreshToken.session_id == session_id,
                    RefreshToken.revoked_at.is_(None),
                )
            )
        ).all()
    )
    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )
    await _revoke_tokens(db, tokens)
    db.add(
        ActivityLog(
            user_id=current_user.id,
            module="auth",
            action="revoke_session",
            resource="session",
            resource_id=session_id,
        )
    )
    await db.commit()


@router.post("/sessions/revoke-all", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_all_sessions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await _revoke_all_refresh_tokens(db, current_user.id)
    db.add(
        ActivityLog(
            user_id=current_user.id,
            module="auth",
            action="revoke_all_sessions",
            resource="user",
            resource_id=current_user.id,
        )
    )
    await db.commit()


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    request: ChangePasswordRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    if not verify_password(request.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    if verify_password(request.new_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must differ from the current password",
        )
    current_user.password_hash = hash_password(request.new_password)
    await _revoke_all_refresh_tokens(db, current_user.id)
    db.add(
        ActivityLog(
            user_id=current_user.id,
            module="auth",
            action="change_password",
            resource="user",
            resource_id=current_user.id,
        )
    )
    await db.commit()
