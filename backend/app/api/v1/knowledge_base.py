"""Knowledge Base API: categories, articles, versioning, the publishing
workflow, and article <-> incident linking.

Visibility rule: PUBLISHED articles are readable by anyone authenticated.
DRAFT / IN_REVIEW / ARCHIVED articles are only visible to their author or a
holder of `kb.review`.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.dependencies import (
    get_current_user,
    require_permission,
    user_has_permission,
)
from app.db.models import (
    KBArticle,
    KBArticleIncidentLink,
    KBArticleStatus,
    KBArticleVersion,
    KBCategory,
    Ticket,
    User,
)
from app.db.session import get_db
from app.schemas.knowledge_base import (
    KBArticleArchive,
    KBArticleCreate,
    KBArticleIncidentLinkCreate,
    KBArticleIncidentLinkListResponse,
    KBArticleIncidentLinkResponse,
    KBArticleListResponse,
    KBArticleResponse,
    KBArticleRestore,
    KBArticleReviewDecision,
    KBArticleStatusResponse,
    KBArticleSubmitForReview,
    KBArticleUpdate,
    KBArticleVersionListResponse,
    KBCategoryCreate,
    KBCategoryListResponse,
    KBCategoryResponse,
    KBCategoryUpdate,
)
from app.services.knowledge_base import KnowledgeBaseService

router = APIRouter(tags=["Knowledge Base"])

ARTICLE_LOAD_OPTIONS = (selectinload(KBArticle.status), selectinload(KBArticle.author))


# ==========================================================
# Helpers
# ==========================================================


async def _visible_or_404(db: AsyncSession, user: User, article: KBArticle | None) -> KBArticle:
    if article is None or article.is_deleted:
        raise HTTPException(status_code=404, detail="Article not found")
    if article.status.code == "PUBLISHED":
        return article
    if article.author_id == user.id:
        return article
    if await user_has_permission(db, user.id, "kb.review"):
        return article
    raise HTTPException(status_code=404, detail="Article not found")


async def _get_article_or_404(db: AsyncSession, article_id: UUID) -> KBArticle:
    article = await db.scalar(
        select(KBArticle)
        .where(KBArticle.id == article_id)
        .options(*ARTICLE_LOAD_OPTIONS)
    )
    if article is None or article.is_deleted:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


# ==========================================================
# Categories
# ==========================================================


@router.get("/kb/categories", response_model=KBCategoryListResponse)
async def list_kb_categories(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> KBCategoryListResponse:
    base = select(KBCategory).where(KBCategory.is_deleted.is_(False))
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    items = (
        await db.scalars(
            base.order_by(KBCategory.sort_order, KBCategory.name)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return KBCategoryListResponse(items=items, total=total or 0, page=page, page_size=page_size)


@router.post(
    "/kb/categories", response_model=KBCategoryResponse, status_code=status.HTTP_201_CREATED
)
async def create_kb_category(
    payload: KBCategoryCreate,
    current_user: Annotated[User, Depends(require_permission("kb.create"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> KBCategory:
    if payload.parent_id is not None:
        parent = await db.get(KBCategory, payload.parent_id)
        if parent is None or parent.is_deleted:
            raise HTTPException(status_code=400, detail="Invalid parent_id")
    category = KBCategory(**payload.model_dump(), created_by=current_user.id)
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


@router.put("/kb/categories/{category_id}", response_model=KBCategoryResponse)
async def update_kb_category(
    category_id: UUID,
    payload: KBCategoryUpdate,
    current_user: Annotated[User, Depends(require_permission("kb.update"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> KBCategory:
    category = await db.get(KBCategory, category_id)
    if category is None or category.is_deleted:
        raise HTTPException(status_code=404, detail="Category not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(category, field, value)
    category.updated_by = current_user.id
    await db.commit()
    await db.refresh(category)
    return category


@router.delete("/kb/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_kb_category(
    category_id: UUID,
    current_user: Annotated[User, Depends(require_permission("kb.delete"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    category = await db.get(KBCategory, category_id)
    if category is None or category.is_deleted:
        raise HTTPException(status_code=404, detail="Category not found")
    category.is_deleted = True
    category.deleted_by = current_user.id
    await db.commit()


# ==========================================================
# Articles
# ==========================================================


@router.get("/kb/articles", response_model=KBArticleListResponse)
async def list_kb_articles(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    q: str | None = Query(default=None, min_length=1, max_length=200),
    category_id: UUID | None = None,
    status_code: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> KBArticleListResponse:
    can_review = await user_has_permission(db, current_user.id, "kb.review")

    conditions = [KBArticle.is_deleted.is_(False)]
    if not can_review:
        conditions.append(
            (KBArticleStatus.code == "PUBLISHED") | (KBArticle.author_id == current_user.id)
        )
    if category_id is not None:
        conditions.append(KBArticle.category_id == category_id)
    if status_code is not None:
        conditions.append(KBArticleStatus.code == status_code)
    if q:
        like = f"%{q}%"
        conditions.append(KBArticle.title.ilike(like))

    base = select(KBArticle).join(KBArticleStatus).where(*conditions)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    items = (
        await db.scalars(
            base.options(*ARTICLE_LOAD_OPTIONS)
            .order_by(KBArticle.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return KBArticleListResponse(items=items, total=total or 0, page=page, page_size=page_size)


@router.post(
    "/kb/articles", response_model=KBArticleResponse, status_code=status.HTTP_201_CREATED
)
async def create_kb_article(
    payload: KBArticleCreate,
    current_user: Annotated[User, Depends(require_permission("kb.create"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> KBArticle:
    category = await db.get(KBCategory, payload.category_id)
    if category is None or category.is_deleted:
        raise HTTPException(status_code=400, detail="Invalid category_id")

    service = KnowledgeBaseService(db)
    draft_status = await service.get_status_by_code("DRAFT")

    article = KBArticle(
        **payload.model_dump(),
        status_id=draft_status.id,
        author_id=current_user.id,
        created_by=current_user.id,
    )
    db.add(article)
    await db.commit()
    article = await _get_article_or_404(db, article.id)
    return article


@router.get("/kb/articles/{article_id}", response_model=KBArticleResponse)
async def get_kb_article(
    article_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> KBArticle:
    article = await _get_article_or_404(db, article_id)
    article = await _visible_or_404(db, current_user, article)
    if article.status.code == "PUBLISHED":
        article.view_count += 1
        await db.commit()
        article = await _get_article_or_404(db, article_id)
    return article


@router.put("/kb/articles/{article_id}", response_model=KBArticleResponse)
async def update_kb_article(
    article_id: UUID,
    payload: KBArticleUpdate,
    current_user: Annotated[User, Depends(require_permission("kb.update"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> KBArticle:
    """Plain edit: updates the current draft in place, no version snapshot
    (see KBArticleUpdate docstring)."""
    article = await _get_article_or_404(db, article_id)
    if article.author_id != current_user.id and not await user_has_permission(
        db, current_user.id, "kb.review"
    ):
        raise HTTPException(status_code=403, detail="Only the author or a reviewer may edit")

    updates = payload.model_dump(exclude_unset=True)
    if "category_id" in updates and updates["category_id"] is not None:
        category = await db.get(KBCategory, updates["category_id"])
        if category is None or category.is_deleted:
            raise HTTPException(status_code=400, detail="Invalid category_id")
    for field, value in updates.items():
        setattr(article, field, value)
    article.updated_by = current_user.id
    await db.commit()
    article = await _get_article_or_404(db, article_id)
    return article


@router.delete("/kb/articles/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_kb_article(
    article_id: UUID,
    current_user: Annotated[User, Depends(require_permission("kb.delete"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    article = await db.get(KBArticle, article_id)
    if article is None or article.is_deleted:
        raise HTTPException(status_code=404, detail="Article not found")
    article.is_deleted = True
    article.deleted_by = current_user.id
    await db.commit()


# ==========================================================
# Versioning
# ==========================================================


@router.get("/kb/articles/{article_id}/versions", response_model=KBArticleVersionListResponse)
async def list_kb_article_versions(
    article_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> KBArticleVersionListResponse:
    article = await _get_article_or_404(db, article_id)
    await _visible_or_404(db, current_user, article)
    items = (
        await db.scalars(
            select(KBArticleVersion)
            .where(KBArticleVersion.article_id == article_id, KBArticleVersion.is_deleted.is_(False))
            .options(selectinload(KBArticleVersion.changed_by))
            .order_by(KBArticleVersion.version_no.desc())
        )
    ).all()
    return KBArticleVersionListResponse(items=items, total=len(items))


# ==========================================================
# Publishing Workflow
# ==========================================================


@router.post("/kb/articles/{article_id}/submit", response_model=KBArticleStatusResponse)
async def submit_kb_article_for_review(
    article_id: UUID,
    payload: KBArticleSubmitForReview,
    current_user: Annotated[User, Depends(require_permission("kb.submit"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> KBArticle:
    article = await _get_article_or_404(db, article_id)
    if article.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the author may submit for review")
    service = KnowledgeBaseService(db)
    await service.transition(
        article,
        "IN_REVIEW",
        current_user,
        required_permission="kb.submit",
        snapshot_version=True,
        change_summary=payload.note,
    )
    return await _get_article_or_404(db, article_id)


@router.post("/kb/articles/{article_id}/review", response_model=KBArticleStatusResponse)
async def review_kb_article(
    article_id: UUID,
    payload: KBArticleReviewDecision,
    current_user: Annotated[User, Depends(require_permission("kb.review"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> KBArticle:
    article = await _get_article_or_404(db, article_id)
    service = KnowledgeBaseService(db)
    if payload.approve:
        await service.transition(
            article,
            "PUBLISHED",
            current_user,
            required_permission="kb.review",
            snapshot_version=True,
            change_summary=payload.comment,
            set_published_at=True,
        )
    else:
        await service.transition(
            article,
            "DRAFT",
            current_user,
            required_permission="kb.review",
        )
    return await _get_article_or_404(db, article_id)


@router.post("/kb/articles/{article_id}/archive", response_model=KBArticleStatusResponse)
async def archive_kb_article(
    article_id: UUID,
    payload: KBArticleArchive,
    current_user: Annotated[User, Depends(require_permission("kb.archive"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> KBArticle:
    article = await _get_article_or_404(db, article_id)
    service = KnowledgeBaseService(db)
    await service.transition(
        article,
        "ARCHIVED",
        current_user,
        required_permission="kb.archive",
    )
    return await _get_article_or_404(db, article_id)


@router.post("/kb/articles/{article_id}/restore", response_model=KBArticleStatusResponse)
async def restore_kb_article(
    article_id: UUID,
    payload: KBArticleRestore,
    current_user: Annotated[User, Depends(require_permission("kb.restore"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> KBArticle:
    article = await _get_article_or_404(db, article_id)
    service = KnowledgeBaseService(db)
    await service.transition(
        article,
        "DRAFT",
        current_user,
        required_permission="kb.restore",
        clear_published_at=True,
    )
    return await _get_article_or_404(db, article_id)


# ==========================================================
# Article <-> Incident
# ==========================================================


@router.post(
    "/kb/articles/{article_id}/incidents",
    response_model=KBArticleIncidentLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def link_kb_article_to_incident(
    article_id: UUID,
    payload: KBArticleIncidentLinkCreate,
    current_user: Annotated[User, Depends(require_permission("kb.link_incident"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> KBArticleIncidentLink:
    if payload.article_id != article_id:
        raise HTTPException(status_code=400, detail="article_id mismatch")
    article = await _get_article_or_404(db, article_id)
    ticket = await db.get(Ticket, payload.ticket_id)
    if ticket is None or ticket.is_deleted:
        raise HTTPException(status_code=400, detail="Invalid ticket_id")

    service = KnowledgeBaseService(db)
    link = await service.link_incident(article.id, ticket.id, current_user, note=payload.note)
    link = await db.scalar(
        select(KBArticleIncidentLink)
        .where(KBArticleIncidentLink.id == link.id)
        .options(
            selectinload(KBArticleIncidentLink.article).selectinload(KBArticle.status),
            selectinload(KBArticleIncidentLink.linked_by),
        )
    )
    return link


@router.delete(
    "/kb/articles/{article_id}/incidents/{ticket_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unlink_kb_article_from_incident(
    article_id: UUID,
    ticket_id: UUID,
    current_user: Annotated[User, Depends(require_permission("kb.link_incident"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    link = await db.scalar(
        select(KBArticleIncidentLink).where(
            KBArticleIncidentLink.article_id == article_id,
            KBArticleIncidentLink.ticket_id == ticket_id,
            KBArticleIncidentLink.is_deleted.is_(False),
        )
    )
    if link is None:
        raise HTTPException(status_code=404, detail="Link not found")
    link.is_deleted = True
    link.deleted_by = current_user.id
    await db.commit()


@router.get(
    "/kb/articles/{article_id}/incidents",
    response_model=KBArticleIncidentLinkListResponse,
)
async def list_kb_article_incidents(
    article_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> KBArticleIncidentLinkListResponse:
    article = await _get_article_or_404(db, article_id)
    await _visible_or_404(db, current_user, article)
    items = (
        await db.scalars(
            select(KBArticleIncidentLink)
            .where(
                KBArticleIncidentLink.article_id == article_id,
                KBArticleIncidentLink.is_deleted.is_(False),
            )
            .options(
                selectinload(KBArticleIncidentLink.article).selectinload(KBArticle.status),
                selectinload(KBArticleIncidentLink.linked_by),
            )
            .order_by(KBArticleIncidentLink.linked_at.desc())
        )
    ).all()
    return KBArticleIncidentLinkListResponse(items=items, total=len(items))


@router.get(
    "/tickets/{ticket_id}/kb-articles",
    response_model=KBArticleIncidentLinkListResponse,
)
async def list_incident_kb_articles(
    ticket_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> KBArticleIncidentLinkListResponse:
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None or ticket.is_deleted:
        raise HTTPException(status_code=404, detail="Ticket not found")
    items = (
        await db.scalars(
            select(KBArticleIncidentLink)
            .where(
                KBArticleIncidentLink.ticket_id == ticket_id,
                KBArticleIncidentLink.is_deleted.is_(False),
            )
            .options(
                selectinload(KBArticleIncidentLink.article).selectinload(KBArticle.status),
                selectinload(KBArticleIncidentLink.linked_by),
            )
            .order_by(KBArticleIncidentLink.linked_at.desc())
        )
    ).all()
    return KBArticleIncidentLinkListResponse(items=items, total=len(items))