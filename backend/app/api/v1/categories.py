from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, require_permission
from app.db.models import TicketCategory, TicketService, TicketSubcategory, User
from app.db.session import get_db

router = APIRouter(tags=["Categories"])


class CategoryResponse(BaseModel):
    id: UUID
    code: str
    name: str
    color: str | None
    icon: str | None
    sort_order: int
    is_active: bool
    model_config = ConfigDict(from_attributes=True)


class CategoryRequest(BaseModel):
    code: str = Field(..., min_length=2, max_length=50, pattern=r"^[A-Z0-9_]+$")
    name: str = Field(..., min_length=3, max_length=100)
    color: str | None = Field(None, max_length=20)
    icon: str | None = Field(None, max_length=100)
    sort_order: int = 0
    is_active: bool = True


class SubcategoryResponse(BaseModel):
    id: UUID
    category_id: UUID
    code: str
    name: str
    sort_order: int
    is_active: bool
    model_config = ConfigDict(from_attributes=True)


class SubcategoryRequest(BaseModel):
    category_id: UUID
    code: str = Field(..., min_length=2, max_length=50, pattern=r"^[A-Z0-9_]+$")
    name: str = Field(..., min_length=3, max_length=100)
    sort_order: int = 0
    is_active: bool = True


class ServiceResponse(BaseModel):
    id: UUID
    subcategory_id: UUID
    code: str
    name: str
    description: str | None
    sort_order: int
    is_active: bool
    model_config = ConfigDict(from_attributes=True)


class ServiceRequest(BaseModel):
    subcategory_id: UUID
    code: str = Field(..., min_length=2, max_length=50, pattern=r"^[A-Z0-9_]+$")
    name: str = Field(..., min_length=3, max_length=100)
    description: str | None = Field(None, max_length=2000)
    sort_order: int = 0
    is_active: bool = True


async def _active_parent_or_400(db: AsyncSession, model, record_id: UUID, label: str):
    record = await db.scalar(
        select(model).where(
            model.id == record_id,
            model.is_active.is_(True),
            model.is_deleted.is_(False),
        )
    )
    if record is None:
        raise HTTPException(status_code=400, detail=f"Invalid {label}")
    return record


async def _soft_delete(model, record_id: UUID, current_user: User, db: AsyncSession, label: str):
    record = await db.get(model, record_id)
    if record is None or record.is_deleted:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    record.is_deleted = True
    record.deleted_by = current_user.id
    await db.commit()


@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TicketCategory]:
    return (
        await db.scalars(
            select(TicketCategory)
            .where(
                TicketCategory.is_deleted.is_(False), TicketCategory.is_active.is_(True)
            )
            .order_by(TicketCategory.sort_order, TicketCategory.name)
        )
    ).all()


@router.post(
    "/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED
)
async def create_category(
    payload: CategoryRequest,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketCategory:
    if await db.scalar(
        select(TicketCategory).where(TicketCategory.code == payload.code)
    ):
        raise HTTPException(status_code=409, detail="Category code already exists")
    category = TicketCategory(**payload.model_dump(), created_by=current_user.id)
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


@router.put("/categories/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: UUID,
    payload: CategoryRequest,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketCategory:
    category = await db.get(TicketCategory, category_id)
    if not category or category.is_deleted:
        raise HTTPException(status_code=404, detail="Category not found")
    for key, value in payload.model_dump().items():
        setattr(category, key, value)
    category.updated_by = current_user.id
    await db.commit()
    await db.refresh(category)
    return category


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: UUID,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await _soft_delete(TicketCategory, category_id, current_user, db, "Category")


@router.get("/subcategories", response_model=list[SubcategoryResponse])
async def list_subcategories(
    category_id: UUID | None = None,
    include_inactive: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TicketSubcategory]:
    conditions = [TicketSubcategory.is_deleted.is_(False)]
    if category_id:
        conditions.append(TicketSubcategory.category_id == category_id)
    if not include_inactive:
        conditions.append(TicketSubcategory.is_active.is_(True))
    return list(
        (await db.scalars(select(TicketSubcategory).where(*conditions).order_by(
            TicketSubcategory.sort_order, TicketSubcategory.name
        ))).all()
    )


@router.post("/subcategories", response_model=SubcategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_subcategory(
    payload: SubcategoryRequest,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketSubcategory:
    await _active_parent_or_400(db, TicketCategory, payload.category_id, "category")
    exists = await db.scalar(select(TicketSubcategory).where(
        TicketSubcategory.category_id == payload.category_id,
        TicketSubcategory.code == payload.code,
    ))
    if exists:
        raise HTTPException(status_code=409, detail="Subcategory code already exists in this category")
    record = TicketSubcategory(**payload.model_dump(), created_by=current_user.id)
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


@router.put("/subcategories/{subcategory_id}", response_model=SubcategoryResponse)
async def update_subcategory(
    subcategory_id: UUID,
    payload: SubcategoryRequest,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketSubcategory:
    record = await db.get(TicketSubcategory, subcategory_id)
    if record is None or record.is_deleted:
        raise HTTPException(status_code=404, detail="Subcategory not found")
    await _active_parent_or_400(db, TicketCategory, payload.category_id, "category")
    for key, value in payload.model_dump().items():
        setattr(record, key, value)
    record.updated_by = current_user.id
    await db.commit()
    await db.refresh(record)
    return record


@router.delete("/subcategories/{subcategory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subcategory(
    subcategory_id: UUID,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await _soft_delete(TicketSubcategory, subcategory_id, current_user, db, "Subcategory")


@router.get("/services", response_model=list[ServiceResponse])
async def list_services(
    subcategory_id: UUID | None = None,
    include_inactive: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TicketService]:
    conditions = [TicketService.is_deleted.is_(False)]
    if subcategory_id:
        conditions.append(TicketService.subcategory_id == subcategory_id)
    if not include_inactive:
        conditions.append(TicketService.is_active.is_(True))
    return list((await db.scalars(select(TicketService).where(*conditions).order_by(
        TicketService.sort_order, TicketService.name
    ))).all())


@router.post("/services", response_model=ServiceResponse, status_code=status.HTTP_201_CREATED)
async def create_service(
    payload: ServiceRequest,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketService:
    await _active_parent_or_400(db, TicketSubcategory, payload.subcategory_id, "subcategory")
    exists = await db.scalar(select(TicketService).where(
        TicketService.subcategory_id == payload.subcategory_id,
        TicketService.code == payload.code,
    ))
    if exists:
        raise HTTPException(status_code=409, detail="Service code already exists in this subcategory")
    record = TicketService(**payload.model_dump(), created_by=current_user.id)
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


@router.put("/services/{service_id}", response_model=ServiceResponse)
async def update_service(
    service_id: UUID,
    payload: ServiceRequest,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketService:
    record = await db.get(TicketService, service_id)
    if record is None or record.is_deleted:
        raise HTTPException(status_code=404, detail="Service not found")
    await _active_parent_or_400(db, TicketSubcategory, payload.subcategory_id, "subcategory")
    for key, value in payload.model_dump().items():
        setattr(record, key, value)
    record.updated_by = current_user.id
    await db.commit()
    await db.refresh(record)
    return record


@router.delete("/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(
    service_id: UUID,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await _soft_delete(TicketService, service_id, current_user, db, "Service")
