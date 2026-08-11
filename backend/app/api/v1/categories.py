from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, require_permission
from app.db.models import TicketCategory, TicketService, TicketSubcategory, User
from app.db.session import get_db
from app.schemas.references.category import CategoryCreate, CategoryResponse
from app.schemas.references.service import ServiceCreate, ServiceResponse
from app.schemas.references.subcategory import SubcategoryCreate, SubcategoryResponse

router = APIRouter(tags=["Categories"])


# ==========================================================
# Helpers
# ==========================================================


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


async def _assert_code_available(
    db: AsyncSession,
    model,
    code: str,
    *,
    exclude_id: UUID | None = None,
    scope_field: str | None = None,
    scope_value: UUID | None = None,
    label: str,
) -> None:
    """
    Raise 409 if another non-deleted record already uses this code.

    Soft-deleted records never block reuse of their code. `scope_field` /
    `scope_value` restrict the uniqueness check to siblings under the same
    parent (e.g. code unique per category for subcategories).
    """

    conditions = [model.code == code, model.is_deleted.is_(False)]

    if scope_field is not None:
        conditions.append(getattr(model, scope_field) == scope_value)

    if exclude_id is not None:
        conditions.append(model.id != exclude_id)

    if await db.scalar(select(model).where(*conditions)):
        raise HTTPException(status_code=409, detail=f"{label} code already exists")


# ==========================================================
# Categories
# ==========================================================


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
    payload: CategoryCreate,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketCategory:
    await _assert_code_available(db, TicketCategory, payload.code, label="Category")
    category = TicketCategory(**payload.model_dump(), created_by=current_user.id)
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


@router.put("/categories/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: UUID,
    payload: CategoryCreate,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketCategory:
    category = await db.get(TicketCategory, category_id)
    if not category or category.is_deleted:
        raise HTTPException(status_code=404, detail="Category not found")
    await _assert_code_available(
        db, TicketCategory, payload.code, exclude_id=category_id, label="Category"
    )
    for key, value in payload.model_dump().items():
        setattr(category, key, value)
    category.updated_by = current_user.id
    await db.commit()
    await db.refresh(category)
    return category


@router.delete(
    "/categories/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_category(
    category_id: UUID,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await _soft_delete(TicketCategory, category_id, current_user, db, "Category")


# ==========================================================
# Subcategories
# ==========================================================


@router.get("/subcategories", response_model=list[SubcategoryResponse])
async def list_subcategories(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    category_id: Annotated[UUID | None, Query()] = None,
    include_inactive: Annotated[bool, Query()] = False,
) -> list[TicketSubcategory]:
    conditions = [TicketSubcategory.is_deleted.is_(False)]
    if category_id:
        conditions.append(TicketSubcategory.category_id == category_id)
    if not include_inactive:
        conditions.append(TicketSubcategory.is_active.is_(True))
    return list(
        (
            await db.scalars(
                select(TicketSubcategory)
                .where(*conditions)
                .order_by(TicketSubcategory.sort_order, TicketSubcategory.name)
            )
        ).all()
    )


@router.post(
    "/subcategories",
    response_model=SubcategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_subcategory(
    payload: SubcategoryCreate,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketSubcategory:
    await _active_parent_or_400(db, TicketCategory, payload.category_id, "category")
    await _assert_code_available(
        db,
        TicketSubcategory,
        payload.code,
        scope_field="category_id",
        scope_value=payload.category_id,
        label="Subcategory",
    )
    record = TicketSubcategory(**payload.model_dump(), created_by=current_user.id)
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


@router.put("/subcategories/{subcategory_id}", response_model=SubcategoryResponse)
async def update_subcategory(
    subcategory_id: UUID,
    payload: SubcategoryCreate,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketSubcategory:
    record = await db.get(TicketSubcategory, subcategory_id)
    if record is None or record.is_deleted:
        raise HTTPException(status_code=404, detail="Subcategory not found")
    await _active_parent_or_400(db, TicketCategory, payload.category_id, "category")
    await _assert_code_available(
        db,
        TicketSubcategory,
        payload.code,
        exclude_id=subcategory_id,
        scope_field="category_id",
        scope_value=payload.category_id,
        label="Subcategory",
    )
    for key, value in payload.model_dump().items():
        setattr(record, key, value)
    record.updated_by = current_user.id
    await db.commit()
    await db.refresh(record)
    return record


@router.delete(
    "/subcategories/{subcategory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_subcategory(
    subcategory_id: UUID,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await _soft_delete(TicketSubcategory, subcategory_id, current_user, db, "Subcategory")


# ==========================================================
# Services
# ==========================================================


@router.get("/services", response_model=list[ServiceResponse])
async def list_services(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    subcategory_id: Annotated[UUID | None, Query()] = None,
    include_inactive: Annotated[bool, Query()] = False,
) -> list[TicketService]:
    conditions = [TicketService.is_deleted.is_(False)]
    if subcategory_id:
        conditions.append(TicketService.subcategory_id == subcategory_id)
    if not include_inactive:
        conditions.append(TicketService.is_active.is_(True))
    return list(
        (
            await db.scalars(
                select(TicketService)
                .where(*conditions)
                .order_by(TicketService.sort_order, TicketService.name)
            )
        ).all()
    )


@router.post(
    "/services", response_model=ServiceResponse, status_code=status.HTTP_201_CREATED
)
async def create_service(
    payload: ServiceCreate,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketService:
    await _active_parent_or_400(db, TicketSubcategory, payload.subcategory_id, "subcategory")
    await _assert_code_available(
        db,
        TicketService,
        payload.code,
        scope_field="subcategory_id",
        scope_value=payload.subcategory_id,
        label="Service",
    )
    record = TicketService(**payload.model_dump(), created_by=current_user.id)
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


@router.put("/services/{service_id}", response_model=ServiceResponse)
async def update_service(
    service_id: UUID,
    payload: ServiceCreate,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketService:
    record = await db.get(TicketService, service_id)
    if record is None or record.is_deleted:
        raise HTTPException(status_code=404, detail="Service not found")
    await _active_parent_or_400(db, TicketSubcategory, payload.subcategory_id, "subcategory")
    await _assert_code_available(
        db,
        TicketService,
        payload.code,
        exclude_id=service_id,
        scope_field="subcategory_id",
        scope_value=payload.subcategory_id,
        label="Service",
    )
    for key, value in payload.model_dump().items():
        setattr(record, key, value)
    record.updated_by = current_user.id
    await db.commit()
    await db.refresh(record)
    return record


@router.delete(
    "/services/{service_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_service(
    service_id: UUID,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await _soft_delete(TicketService, service_id, current_user, db, "Service")