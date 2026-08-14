"""HTTP API for SLA configuration and live ticket timers."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.dependencies import get_current_user, require_permission
from app.db.models import (
    SLAEscalationEvent,
    SLAEscalationTrigger,
    SLAPauseRule,
    SLAPolicy,
    SLATarget,
    Ticket,
    TicketSlaTimer,
    TicketStatus,
    User,
)
from app.db.session import get_db
from app.schemas.sla_escalation import (
    SLAEscalationEventListResponse,
    SLAEscalationTriggerCreate,
    SLAEscalationTriggerListResponse,
    SLAEscalationTriggerResponse,
    SLAEscalationTriggerUpdate,
)
from app.schemas.references.sla_policy import (
    SLAPauseRuleCreate,
    SLAPauseRuleListResponse,
    SLAPauseRuleResponse,
    SLAPauseRuleUpdate,
    SLAPolicyCreate,
    SLAPolicyListResponse,
    SLAPolicyResponse,
    SLAPolicyUpdate,
    SLATargetResponse,
    SLATargetUpdate,
)
from app.schemas.ticket import TicketSlaStatus, TicketSlaTimerSummary
from app.services.async_sla import (
    cancel_timer,
    mark_timer_met,
    pause_timer,
    resume_timer,
)

router = APIRouter(tags=["SLA"])


async def _policy_or_404(db: AsyncSession, policy_id: UUID) -> SLAPolicy:
    policy = await db.scalar(
        select(SLAPolicy)
        .where(SLAPolicy.id == policy_id, SLAPolicy.is_deleted.is_(False))
        .options(selectinload(SLAPolicy.targets))
    )
    if policy is None:
        raise HTTPException(status_code=404, detail="SLA policy not found")
    return policy


async def _timer_or_404(db: AsyncSession, timer_id: UUID) -> TicketSlaTimer:
    timer = await db.scalar(
        select(TicketSlaTimer).where(
            TicketSlaTimer.id == timer_id,
            TicketSlaTimer.is_deleted.is_(False),
        )
    )
    if timer is None:
        raise HTTPException(status_code=404, detail="SLA timer not found")
    return timer


async def _ticket_or_404(db: AsyncSession, ticket_id: UUID) -> Ticket:
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None or ticket.is_deleted:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.get("/sla/policies", response_model=SLAPolicyListResponse)
async def list_policies(
    _: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> SLAPolicyListResponse:
    total = await db.scalar(
        select(func.count()).select_from(SLAPolicy).where(SLAPolicy.is_deleted.is_(False))
    )
    policies = (
        await db.scalars(
            select(SLAPolicy)
            .where(SLAPolicy.is_deleted.is_(False))
            .options(selectinload(SLAPolicy.targets))
            .order_by(SLAPolicy.match_priority, SLAPolicy.created_at)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return SLAPolicyListResponse(
        items=list(policies), total=total or 0, page=page, page_size=page_size
    )


@router.get("/sla/policies/{policy_id}", response_model=SLAPolicyResponse)
async def get_policy(
    policy_id: UUID,
    _: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SLAPolicy:
    return await _policy_or_404(db, policy_id)


@router.post(
    "/sla/policies",
    response_model=SLAPolicyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_policy(
    payload: SLAPolicyCreate,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SLAPolicy:
    existing = await db.scalar(
        select(SLAPolicy).where(SLAPolicy.code == payload.code)
    )
    if existing and not existing.is_deleted:
        raise HTTPException(status_code=409, detail="SLA policy code already exists")

    if existing and existing.is_deleted:
        policy = existing
        for field, value in payload.model_dump(exclude={"targets"}).items():
            setattr(policy, field, value)
        policy.is_deleted = False
        policy.deleted_at = None
        policy.deleted_by = None
        policy.updated_by = current_user.id
    else:
        data = payload.model_dump(exclude={"targets"})
        policy = SLAPolicy(**data, created_by=current_user.id)
        db.add(policy)
        await db.flush()

    # Reusing a soft-deleted policy must also reuse its existing target rows,
    # because (policy_id, metric_type) is a database-level unique key.
    existing_targets = {
        target.metric_type: target
        for target in (
            await db.scalars(
                select(SLATarget).where(SLATarget.policy_id == policy.id)
            )
        ).all()
    }
    requested_metrics = set()
    for target_data in payload.targets:
        data = target_data.model_dump()
        metric = data["metric_type"]
        requested_metrics.add(metric)
        target = existing_targets.get(metric)
        if target is None:
            db.add(
                SLATarget(
                    policy_id=policy.id,
                    **data,
                    created_by=current_user.id,
                )
            )
        else:
            for field, value in data.items():
                setattr(target, field, value)
            target.is_deleted = False
            target.deleted_at = None
            target.deleted_by = None
            target.updated_by = current_user.id
    for metric, target in existing_targets.items():
        if metric not in requested_metrics:
            target.is_deleted = True
            target.deleted_by = current_user.id
    await db.commit()
    return await _policy_or_404(db, policy.id)


@router.put("/sla/policies/{policy_id}", response_model=SLAPolicyResponse)
async def update_policy(
    policy_id: UUID,
    payload: SLAPolicyUpdate,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SLAPolicy:
    policy = await _policy_or_404(db, policy_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(policy, field, value)
    policy.updated_by = current_user.id
    await db.commit()
    return await _policy_or_404(db, policy.id)


@router.delete("/sla/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(
    policy_id: UUID,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    policy = await _policy_or_404(db, policy_id)
    policy.is_deleted = True
    policy.is_active = False
    policy.deleted_by = current_user.id
    await db.commit()


@router.put("/sla/targets/{target_id}", response_model=SLATargetResponse)
async def update_target(
    target_id: UUID,
    payload: SLATargetUpdate,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SLATarget:
    target = await db.get(SLATarget, target_id)
    if target is None or target.is_deleted:
        raise HTTPException(status_code=404, detail="SLA target not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(target, field, value)
    target.updated_by = current_user.id
    await db.commit()
    return target


@router.get("/sla/pause-rules", response_model=SLAPauseRuleListResponse)
async def list_pause_rules(
    _: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SLAPauseRuleListResponse:
    rules = (
        await db.scalars(
            select(SLAPauseRule)
            .where(SLAPauseRule.is_deleted.is_(False))
            .options(selectinload(SLAPauseRule.status))
            .order_by(SLAPauseRule.created_at)
        )
    ).all()
    return SLAPauseRuleListResponse(items=list(rules))


@router.post(
    "/sla/pause-rules",
    response_model=SLAPauseRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_pause_rule(
    payload: SLAPauseRuleCreate,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SLAPauseRule:
    policy = await _policy_or_404(db, payload.policy_id)
    status_record = await db.scalar(
        select(TicketStatus).where(
            TicketStatus.id == payload.status_id,
            TicketStatus.is_active.is_(True),
            TicketStatus.is_deleted.is_(False),
        )
    )
    if status_record is None:
        raise HTTPException(status_code=400, detail="Invalid ticket status")
    existing = await db.scalar(
        select(SLAPauseRule).where(
            SLAPauseRule.policy_id == policy.id,
            SLAPauseRule.status_id == status_record.id,
        )
    )
    if existing and not existing.is_deleted:
        raise HTTPException(status_code=409, detail="SLA pause rule already exists")
    if existing:
        rule = existing
        rule.is_deleted = False
        rule.deleted_at = None
        rule.deleted_by = None
        rule.reason = payload.reason
        rule.is_active = payload.is_active
        rule.updated_by = current_user.id
    else:
        rule = SLAPauseRule(**payload.model_dump(), created_by=current_user.id)
        db.add(rule)
    await db.commit()
    rule = await db.scalar(
        select(SLAPauseRule)
        .where(SLAPauseRule.id == rule.id)
        .options(selectinload(SLAPauseRule.status))
    )
    return rule


@router.put("/sla/pause-rules/{rule_id}", response_model=SLAPauseRuleResponse)
async def update_pause_rule(
    rule_id: UUID,
    payload: SLAPauseRuleUpdate,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SLAPauseRule:
    rule = await db.get(SLAPauseRule, rule_id)
    if rule is None or rule.is_deleted:
        raise HTTPException(status_code=404, detail="SLA pause rule not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    rule.updated_by = current_user.id
    await db.commit()
    return await db.scalar(
        select(SLAPauseRule)
        .where(SLAPauseRule.id == rule.id)
        .options(selectinload(SLAPauseRule.status))
    )


@router.delete("/sla/pause-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pause_rule(
    rule_id: UUID,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    rule = await db.get(SLAPauseRule, rule_id)
    if rule is None or rule.is_deleted:
        raise HTTPException(status_code=404, detail="SLA pause rule not found")
    rule.is_deleted = True
    rule.is_active = False
    rule.deleted_by = current_user.id
    await db.commit()


@router.get("/sla/escalation-triggers", response_model=SLAEscalationTriggerListResponse)
async def list_escalation_triggers(
    _: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> SLAEscalationTriggerListResponse:
    stmt = select(SLAEscalationTrigger).where(SLAEscalationTrigger.is_deleted.is_(False))
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = list(
        (
            await db.scalars(
                stmt.order_by(SLAEscalationTrigger.created_at)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return SLAEscalationTriggerListResponse(
        items=items, total=total or 0, page=page, page_size=page_size
    )


@router.post(
    "/sla/escalation-triggers",
    response_model=SLAEscalationTriggerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_escalation_trigger(
    payload: SLAEscalationTriggerCreate,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SLAEscalationTrigger:
    await _policy_or_404(db, payload.policy_id)
    record = SLAEscalationTrigger(**payload.model_dump(), created_by=current_user.id)
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


@router.put(
    "/sla/escalation-triggers/{trigger_id}",
    response_model=SLAEscalationTriggerResponse,
)
async def update_escalation_trigger(
    trigger_id: UUID,
    payload: SLAEscalationTriggerUpdate,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SLAEscalationTrigger:
    record = await db.get(SLAEscalationTrigger, trigger_id)
    if record is None or record.is_deleted:
        raise HTTPException(status_code=404, detail="SLA escalation trigger not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(record, field, value)
    record.updated_by = current_user.id
    await db.commit()
    await db.refresh(record)
    return record


@router.delete(
    "/sla/escalation-triggers/{trigger_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_escalation_trigger(
    trigger_id: UUID,
    current_user: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    record = await db.get(SLAEscalationTrigger, trigger_id)
    if record is None or record.is_deleted:
        raise HTTPException(status_code=404, detail="SLA escalation trigger not found")
    record.is_deleted = True
    record.is_active = False
    record.deleted_by = current_user.id
    await db.commit()


@router.get(
    "/sla/escalation-events",
    response_model=SLAEscalationEventListResponse,
)
async def list_escalation_events(
    _: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    ticket_id: UUID | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> SLAEscalationEventListResponse:
    stmt = select(SLAEscalationEvent)
    if ticket_id:
        stmt = stmt.where(SLAEscalationEvent.ticket_id == ticket_id)
    items = list(
        (await db.scalars(stmt.order_by(SLAEscalationEvent.fired_at.desc()).limit(limit))).all()
    )
    return SLAEscalationEventListResponse(items=items, total=len(items))


@router.get("/tickets/{ticket_id}/sla", response_model=TicketSlaStatus)
async def get_ticket_sla(
    ticket_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketSlaStatus:
    ticket = await _ticket_or_404(db, ticket_id)
    timers = (
        await db.scalars(
            select(TicketSlaTimer)
            .where(
                TicketSlaTimer.ticket_id == ticket_id,
                TicketSlaTimer.is_deleted.is_(False),
            )
            .order_by(TicketSlaTimer.metric_type)
        )
    ).all()
    by_metric = {timer.metric_type: timer for timer in timers}
    return TicketSlaStatus(
        ticket_id=ticket.id,
        sla_breached=ticket.sla_breached,
        response=by_metric.get("RESPONSE"),
        resolution=by_metric.get("RESOLUTION"),
    )


@router.post("/sla/timers/{timer_id}/pause", response_model=TicketSlaTimerSummary)
async def pause_sla_timer_endpoint(
    timer_id: UUID,
    current_user: Annotated[User, Depends(require_permission("ticket.update"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    reason: str | None = Query(default=None, max_length=255),
) -> TicketSlaTimer:
    timer = await _timer_or_404(db, timer_id)
    ticket = await _ticket_or_404(db, timer.ticket_id)
    await pause_timer(db, timer, ticket, actor_id=current_user.id, reason=reason)
    await db.commit()
    await db.refresh(timer)
    return timer


@router.post("/sla/timers/{timer_id}/resume", response_model=TicketSlaTimerSummary)
async def resume_sla_timer_endpoint(
    timer_id: UUID,
    current_user: Annotated[User, Depends(require_permission("ticket.update"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketSlaTimer:
    timer = await _timer_or_404(db, timer_id)
    ticket = await _ticket_or_404(db, timer.ticket_id)
    await resume_timer(db, timer, ticket, actor_id=current_user.id)
    await db.commit()
    await db.refresh(timer)
    return timer


@router.post("/sla/timers/{timer_id}/met", response_model=TicketSlaTimerSummary)
async def met_sla_timer_endpoint(
    timer_id: UUID,
    current_user: Annotated[User, Depends(require_permission("ticket.update"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketSlaTimer:
    timer = await _timer_or_404(db, timer_id)
    ticket = await _ticket_or_404(db, timer.ticket_id)
    await mark_timer_met(db, timer, ticket, actor_id=current_user.id)
    await db.commit()
    await db.refresh(timer)
    return timer


@router.post("/sla/timers/{timer_id}/cancel", response_model=TicketSlaTimerSummary)
async def cancel_sla_timer_endpoint(
    timer_id: UUID,
    current_user: Annotated[User, Depends(require_permission("ticket.update"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    reason: str | None = Query(default=None, max_length=255),
) -> TicketSlaTimer:
    timer = await _timer_or_404(db, timer_id)
    ticket = await _ticket_or_404(db, timer.ticket_id)
    await cancel_timer(db, timer, ticket, actor_id=current_user.id, reason=reason)
    await db.commit()
    await db.refresh(timer)
    return timer


@router.get("/sla/timers", response_model=list[TicketSlaTimerSummary])
async def list_sla_timers(
    _: Annotated[User, Depends(require_permission("configuration.manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    ticket_id: UUID | None = None,
    timer_status: str | None = Query(default=None, alias="status"),
) -> list[TicketSlaTimer]:
    stmt = select(TicketSlaTimer).where(TicketSlaTimer.is_deleted.is_(False))
    if ticket_id:
        stmt = stmt.where(TicketSlaTimer.ticket_id == ticket_id)
    if timer_status:
        stmt = stmt.where(TicketSlaTimer.status == timer_status.upper())
    stmt = stmt.order_by(TicketSlaTimer.due_at)
    return list((await db.scalars(stmt)).all())
