"""Async persistence service for the Change Management aggregate.

The state machine itself remains in ``app.core.change_management``.  This
service is the application-layer adapter: it hydrates the domain aggregate
from SQLAlchemy rows, invokes domain operations, and persists the resulting
state atomically.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.change_management import (
    Approval as DomainApproval,
    ApprovalDecision,
    ApprovalPolicy,
    ChangeRequest as DomainChangeRequest,
    ChangeStatus,
    ChangeType,
    Implementation as DomainImplementation,
    RiskAssessment as DomainRiskAssessment,
    RiskLevel,
    Rollback as DomainRollback,
    ValidationResult as DomainValidationResult,
)
from app.db.models import (
    ChangeApproval,
    ChangeImplementation,
    ChangeRequest,
    ChangeRiskAssessment,
    ChangeRollback,
    ChangeValidation,
    ChangeNumberSequence,
    Problem,
    TicketPriority,
    TicketService,
    User,
)

POLICY = ApprovalPolicy()


class ChangeManagementService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_404(self, change_id: UUID, *, load_children: bool = True) -> ChangeRequest:
        statement = select(ChangeRequest).where(
            ChangeRequest.id == change_id,
            ChangeRequest.is_deleted.is_(False),
        )
        if load_children:
            statement = statement.options(
                selectinload(ChangeRequest.requested_by),
                selectinload(ChangeRequest.priority),
                selectinload(ChangeRequest.service),
                selectinload(ChangeRequest.problem),
                selectinload(ChangeRequest.risk_assessment).selectinload(
                    ChangeRiskAssessment.assessed_by
                ),
                selectinload(ChangeRequest.approvals).selectinload(ChangeApproval.approver),
                selectinload(ChangeRequest.implementation).selectinload(
                    ChangeImplementation.implemented_by
                ),
                selectinload(ChangeRequest.validation).selectinload(
                    ChangeValidation.validated_by
                ),
                selectinload(ChangeRequest.rollback).selectinload(
                    ChangeRollback.initiated_by
                ),
            )
        change = await self.db.scalar(statement)
        if change is None:
            raise HTTPException(status_code=404, detail="Change request not found")
        return change

    async def next_change_number(self) -> str:
        business_date = datetime.now(timezone.utc).date()
        dialect_name = self.db.get_bind().dialect.name
        insert = postgres_insert if dialect_name == "postgresql" else sqlite_insert
        statement = (
            insert(ChangeNumberSequence)
            .values(business_date=business_date, last_value=1)
            .on_conflict_do_update(
                index_elements=[ChangeNumberSequence.business_date],
                set_={"last_value": ChangeNumberSequence.last_value + 1},
            )
            .returning(ChangeNumberSequence.last_value)
        )
        value = await self.db.scalar(statement)
        return f"CHG-{business_date:%Y%m%d}-{value:06d}"

    async def validate_references(
        self,
        *,
        priority_id: UUID,
        service_id: UUID | None,
        problem_id: UUID | None,
    ) -> None:
        priority = await self.db.get(TicketPriority, priority_id)
        if priority is None or priority.is_deleted:
            raise HTTPException(status_code=400, detail="Invalid priority_id")
        if not priority.is_active:
            raise HTTPException(status_code=400, detail="priority_id is inactive")
        if service_id is not None:
            service = await self.db.get(TicketService, service_id)
            if service is None or service.is_deleted:
                raise HTTPException(status_code=400, detail="Invalid service_id")
            if not service.is_active:
                raise HTTPException(status_code=400, detail="service_id is inactive")
        if problem_id is not None:
            problem = await self.db.get(Problem, problem_id)
            if problem is None or problem.is_deleted:
                raise HTTPException(status_code=400, detail="Invalid problem_id")

    def _aggregate(self, change: ChangeRequest) -> DomainChangeRequest:
        risk = None
        if change.risk_assessment:
            risk = DomainRiskAssessment(
                risk_level=RiskLevel(change.risk_assessment.risk_level),
                impact_description=change.risk_assessment.impact_description,
                likelihood=change.risk_assessment.likelihood,
                mitigation_plan=change.risk_assessment.mitigation_plan,
                assessed_by=str(change.risk_assessment.assessed_by_id),
                assessed_at=change.risk_assessment.created_at,
            )

        approvals = [
            DomainApproval(
                approver=str(row.approver_id),
                decision=ApprovalDecision(row.decision),
                comments=row.comments,
                decided_at=row.decided_at or row.created_at,
            )
            for row in change.approvals
            if not row.is_deleted
        ]

        implementation = None
        if change.implementation:
            implementation = DomainImplementation(
                implementation_plan=change.implementation.implementation_plan,
                scheduled_start=change.implementation.scheduled_start,
                scheduled_end=change.implementation.scheduled_end,
                started_at=change.implementation.started_at,
                completed_at=change.implementation.completed_at,
                notes=change.implementation.notes,
            )

        validation = None
        if change.validation:
            validation = DomainValidationResult(
                validated_by=str(change.validation.validated_by_id),
                validation_result=change.validation.validation_result,
                notes=change.validation.notes,
                validated_at=change.validation.validated_at,
            )

        rollback = None
        if change.rollback:
            rollback = DomainRollback(
                reason=change.rollback.reason,
                rollback_plan=change.rollback.rollback_plan,
                initiated_by=str(change.rollback.initiated_by_id),
                rolled_back_at=change.rollback.rolled_back_at,
            )

        return DomainChangeRequest(
            change_no=change.change_no,
            title=change.title,
            change_type=ChangeType(change.change_type),
            status=ChangeStatus(change.status),
            risk_assessment=risk,
            approvals=approvals,
            implementation=implementation,
            validation=validation,
            rollback=rollback,
            emergency_justification=change.emergency_justification,
        )

    @staticmethod
    def _apply_status(change: ChangeRequest, aggregate: DomainChangeRequest) -> None:
        change.status = aggregate.status.value
        change.risk_level = (
            aggregate.risk_assessment.risk_level.value
            if aggregate.risk_assessment
            else None
        )
        change.emergency_justification = aggregate.emergency_justification

    async def submit(self, change: ChangeRequest, actor: User) -> ChangeRequest:
        aggregate = self._aggregate(change)
        try:
            aggregate.submit()
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        self._apply_status(change, aggregate)
        change.updated_by = actor.id
        await self.db.commit()
        return await self.get_or_404(change.id)

    async def assess_risk(
        self,
        change: ChangeRequest,
        actor: User,
        *,
        risk_level: RiskLevel,
        impact_description: str,
        likelihood: str,
        mitigation_plan: str | None,
    ) -> ChangeRiskAssessment:
        if change.risk_assessment and not change.risk_assessment.is_deleted:
            raise HTTPException(status_code=409, detail="Risk assessment already exists")

        aggregate = self._aggregate(change)

        try:
            result = aggregate.assess_risk(
                risk_level=risk_level,
                impact_description=impact_description,
                likelihood=likelihood,
                assessed_by=str(actor.id),
                mitigation_plan=mitigation_plan,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        row = ChangeRiskAssessment(
            change_request_id=change.id,
            risk_level=result.risk_level.value,
            impact_description=result.impact_description,
            likelihood=result.likelihood,
            mitigation_plan=result.mitigation_plan,
            assessed_by_id=actor.id,
            created_by=actor.id,
        )

        self._apply_status(change, aggregate)
        change.updated_by = actor.id

        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)

        return row

    async def approve(
        self,
        change: ChangeRequest,
        actor: User,
        *,
        decision: ApprovalDecision,
        comments: str | None,
        emergency_justification: str | None,
    ) -> ChangeRequest:
        duplicate = await self.db.scalar(
            select(ChangeApproval).where(
                ChangeApproval.change_request_id == change.id,
                ChangeApproval.approver_id == actor.id,
                ChangeApproval.is_deleted.is_(False),
            )
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="User has already decided on this change")

        aggregate = self._aggregate(change)
        try:
            result = aggregate.record_approval(
                approver=str(actor.id),
                decision=decision,
                policy=POLICY,
                comments=comments,
                emergency_justification=emergency_justification,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        row = ChangeApproval(
            change_request_id=change.id,
            approver_id=actor.id,
            decision=result.decision.value,
            comments=result.comments,
            decided_at=result.decided_at,
            created_by=actor.id,
        )
        self._apply_status(change, aggregate)
        change.updated_by = actor.id
        self.db.add(row)
        await self.db.commit()
        return await self.get_or_404(change.id)

    async def create_implementation(
        self,
        change: ChangeRequest,
        actor: User,
        *,
        implementation_plan: str,
        scheduled_start: datetime | None,
        scheduled_end: datetime | None,
    ) -> ChangeRequest:
        if change.implementation and not change.implementation.is_deleted:
            raise HTTPException(status_code=409, detail="Implementation plan already exists")
        if scheduled_start and scheduled_end and scheduled_end <= scheduled_start:
            raise HTTPException(status_code=422, detail="scheduled_end must be after scheduled_start")
        aggregate = self._aggregate(change)
        try:
            result = aggregate.create_implementation_plan(
                implementation_plan, scheduled_start, scheduled_end
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        self.db.add(
            ChangeImplementation(
                change_request_id=change.id,
                implementation_plan=result.implementation_plan,
                scheduled_start=result.scheduled_start,
                scheduled_end=result.scheduled_end,
                created_by=actor.id,
            )
        )
        change.updated_by = actor.id
        await self.db.commit()
        return await self.get_or_404(change.id)

    async def schedule(self, change: ChangeRequest, actor: User) -> ChangeRequest:
        aggregate = self._aggregate(change)
        try:
            aggregate.schedule()
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        self._apply_status(change, aggregate)
        change.updated_by = actor.id
        await self.db.commit()
        return await self.get_or_404(change.id)

    async def start(self, change: ChangeRequest, actor: User) -> ChangeRequest:
        aggregate = self._aggregate(change)
        try:
            aggregate.start_implementation()
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        assert aggregate.implementation is not None
        row = change.implementation
        assert row is not None
        row.started_at = aggregate.implementation.started_at
        row.implemented_by_id = actor.id
        self._apply_status(change, aggregate)
        change.updated_by = actor.id
        await self.db.commit()
        return await self.get_or_404(change.id)

    async def complete(
        self, change: ChangeRequest, actor: User, notes: str | None
    ) -> ChangeRequest:
        aggregate = self._aggregate(change)
        try:
            aggregate.complete_implementation(notes=notes)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        row = change.implementation
        assert row is not None and aggregate.implementation is not None
        row.completed_at = aggregate.implementation.completed_at
        row.notes = aggregate.implementation.notes
        row.implemented_by_id = row.implemented_by_id or actor.id
        self._apply_status(change, aggregate)
        change.updated_by = actor.id
        await self.db.commit()
        return await self.get_or_404(change.id)

    async def validate(
        self, change: ChangeRequest, actor: User, success: bool, notes: str | None
    ) -> ChangeRequest:
        if change.validation and not change.validation.is_deleted:
            raise HTTPException(status_code=409, detail="Validation already recorded")
        aggregate = self._aggregate(change)
        try:
            result = aggregate.validate(str(actor.id), success, notes)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        self.db.add(
            ChangeValidation(
                change_request_id=change.id,
                validated_by_id=actor.id,
                validation_result=result.validation_result,
                notes=result.notes,
                validated_at=result.validated_at,
                created_by=actor.id,
            )
        )
        self._apply_status(change, aggregate)
        change.updated_by = actor.id
        await self.db.commit()
        return await self.get_or_404(change.id)

    async def initiate_rollback(
        self,
        change: ChangeRequest,
        actor: User,
        reason: str,
        rollback_plan: str,
    ) -> ChangeRequest:
        if change.rollback and not change.rollback.is_deleted:
            raise HTTPException(status_code=409, detail="Rollback already initiated")
        aggregate = self._aggregate(change)
        try:
            result = aggregate.initiate_rollback(reason, rollback_plan, str(actor.id))
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        self.db.add(
            ChangeRollback(
                change_request_id=change.id,
                reason=result.reason,
                rollback_plan=result.rollback_plan,
                initiated_by_id=actor.id,
                created_by=actor.id,
            )
        )
        change.updated_by = actor.id
        await self.db.commit()
        return await self.get_or_404(change.id)

    async def complete_rollback(self, change: ChangeRequest, actor: User) -> ChangeRequest:
        aggregate = self._aggregate(change)
        try:
            aggregate.complete_rollback()
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        row = change.rollback
        assert row is not None and aggregate.rollback is not None
        row.rolled_back_at = aggregate.rollback.rolled_back_at
        self._apply_status(change, aggregate)
        change.updated_by = actor.id
        await self.db.commit()
        return await self.get_or_404(change.id)

    async def close(self, change: ChangeRequest, actor: User) -> ChangeRequest:
        aggregate = self._aggregate(change)
        try:
            aggregate.close()
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        self._apply_status(change, aggregate)
        change.updated_by = actor.id
        await self.db.commit()
        return await self.get_or_404(change.id)

