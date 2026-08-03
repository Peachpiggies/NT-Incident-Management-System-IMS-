from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr

from app.api.v1.dependencies import get_current_user
from app.db.models import User

router = APIRouter(tags=["Users"])


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    role: str
    is_active: bool

    class Config:
        orm_mode = True


@router.get("/users/me", response_model=UserResponse)
async def me(current_user: Annotated[User, Depends(get_current_user)]) -> UserResponse:
    return current_user


@router.get("/roles")
async def list_roles() -> list[str]:
    return [role.value for role in User.__table__.c.role.type.enum_class]
