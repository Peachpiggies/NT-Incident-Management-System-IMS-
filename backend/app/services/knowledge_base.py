"""Knowledge Base service layer.

Publishing status is configurable master data (`KBArticleStatus` /
`KBArticleStatusTransition`), mirroring the ticket workflow tables, so
transitions are enforced against the database-configured edge table rather
than a hardcoded state machine.

Version snapshots are taken only at submit-for-review and at publish time,
not on every plain edit. A submit -> reject -> resubmit -> publish cycle
therefore produces v1 (submitted), v2 (resubmitted), v3 (published) -- the
DRAFT edits in between are not individually versioned.
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    KBArticle,
    KBArticleIncidentLink,
    KBArticleStatus,
    KBArticleStatusTransition,
    KBArticleVersion,
    User,
)


class KnowledgeBaseService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_status_by_code(self, code: str) -> KBArticleStatus:
        article_status = await self.db.scalar(
            select(KBArticleStatus).where(
                KBArticleStatus.code == code,
                KBArticleStatus.is_active.is_(True),
                KBArticleStatus.is_deleted.is_(False),
            )
        )
        if article_status is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"KB article status {code} is not configured",
            )
        return article_status

    async def _snapshot_version(
        self,
        article: KBArticle,
        actor: User,
        *,
        change_summary: str | None,
    ) -> KBArticleVersion:
        next_version_no = article.current_version_no + 1
        version = KBArticleVersion(
            article_id=article.id,
            version_no=next_version_no,
            title=article.title,
            content=article.content,
            change_summary=change_summary,
            changed_by_id=actor.id,
            created_by=actor.id,
        )
        self.db.add(version)
        article.current_version_no = next_version_no
        return version

    async def transition(
        self,
        article: KBArticle,
        to_status_code: str,
        actor: User,
        *,
        required_permission: str,
        snapshot_version: bool = False,
        change_summary: str | None = None,
        set_published_at: bool = False,
        clear_published_at: bool = False,
    ) -> KBArticle:
        """Move `article` to `to_status_code` if a configured, active edge
        exists from its current status, enforcing the edge's
        `required_permission` against the caller-supplied
        `required_permission` (the permission already checked by the
        endpoint's `require_permission` dependency)."""

        to_status = await self.get_status_by_code(to_status_code)

        edge = await self.db.scalar(
            select(KBArticleStatusTransition).where(
                KBArticleStatusTransition.from_status_id == article.status_id,
                KBArticleStatusTransition.to_status_id == to_status.id,
                KBArticleStatusTransition.is_active.is_(True),
                KBArticleStatusTransition.is_deleted.is_(False),
            )
        )
        if edge is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Transition to {to_status_code} is not configured for this article's current status",
            )
        if edge.required_permission and edge.required_permission != required_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {edge.required_permission}",
            )

        if snapshot_version:
            await self._snapshot_version(article, actor, change_summary=change_summary)

        article.status_id = to_status.id
        article.updated_by = actor.id
        if set_published_at:
            from datetime import datetime, timezone

            article.published_at = datetime.now(timezone.utc)
        if clear_published_at:
            article.published_at = None

        await self.db.commit()
        await self.db.refresh(article)
        return article

    async def link_incident(
        self,
        article_id: UUID,
        ticket_id: UUID,
        actor: User,
        *,
        note: str | None = None,
    ) -> KBArticleIncidentLink:
        existing = await self.db.scalar(
            select(KBArticleIncidentLink).where(
                KBArticleIncidentLink.article_id == article_id,
                KBArticleIncidentLink.ticket_id == ticket_id,
                KBArticleIncidentLink.is_deleted.is_(False),
            )
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Article is already linked to this incident",
            )
        link = KBArticleIncidentLink(
            article_id=article_id,
            ticket_id=ticket_id,
            note=note,
            linked_by_id=actor.id,
            created_by=actor.id,
        )
        self.db.add(link)
        await self.db.commit()
        await self.db.refresh(link)
        return link