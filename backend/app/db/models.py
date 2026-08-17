"""Production-grade, UUID-based persistence model for NT-IMS.

The domain uses configurable master data and explicit join tables.  Do not
replace these records with Python enums: administrators must be able to adapt
the business workflow without a deployment.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.session import Base


class BaseModel(Base):
    """Common identity, audit, soft-delete and optimistic-lock fields."""

    __abstract__ = True

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    updated_by: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_by: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class Department(BaseModel):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("code", name="uq_departments_code"),)

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    parent_department_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("departments.id")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    parent: Mapped[Department | None] = relationship(
        remote_side="Department.id", back_populates="children"
    )
    children: Mapped[list[Department]] = relationship(back_populates="parent")
    users: Mapped[list[User]] = relationship(
        back_populates="department", foreign_keys="User.department_id"
    )


class Role(BaseModel):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("code", name="uq_roles_code"),)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    user_roles: Mapped[list[UserRole]] = relationship(back_populates="role")
    role_permissions: Mapped[list[RolePermission]] = relationship(back_populates="role")


class Permission(BaseModel):
    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("code", name="uq_permissions_code"),)

    module: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    role_permissions: Mapped[list[RolePermission]] = relationship(
        back_populates="permission"
    )


class User(BaseModel):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        UniqueConstraint("email", name="uq_users_email"),
    )

    username: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    employee_code: Mapped[str | None] = mapped_column(String(100), unique=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(30))
    department_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("departments.id"), index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    department: Mapped[Department | None] = relationship(
        back_populates="users", foreign_keys=[department_id]
    )
    user_roles: Mapped[list[UserRole]] = relationship(
        back_populates="user", foreign_keys="UserRole.user_id"
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", foreign_keys="RefreshToken.user_id"
    )

    @property
    def full_name(self) -> str:
        """Convenience alias for schemas (e.g. CommentAuthor) that display a
        single display name rather than first_name/last_name separately.
        """
        return f"{self.first_name} {self.last_name}".strip()


class UserRole(BaseModel):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    role_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("roles.id"), nullable=False, index=True
    )
    user: Mapped[User] = relationship(
        back_populates="user_roles", foreign_keys=[user_id]
    )
    role: Mapped[Role] = relationship(back_populates="user_roles")


class RolePermission(BaseModel):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint(
            "role_id", "permission_id", name="uq_role_permissions_role_permission"
        ),
    )
    role_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("roles.id"), nullable=False, index=True
    )
    permission_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("permissions.id"), nullable=False, index=True
    )
    role: Mapped[Role] = relationship(back_populates="role_permissions")
    permission: Mapped[Permission] = relationship(back_populates="role_permissions")


class TicketCategory(BaseModel):
    __tablename__ = "ticket_categories"
    __table_args__ = (UniqueConstraint("code", name="uq_ticket_categories_code"),)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str | None] = mapped_column(String(20))
    icon: Mapped[str | None] = mapped_column(String(100))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tickets: Mapped[list[Ticket]] = relationship(back_populates="category")
    subcategories: Mapped[list[TicketSubcategory]] = relationship(
        back_populates="category"
    )


class TicketSubcategory(BaseModel):
    """A configurable child classification of a ticket category."""

    __tablename__ = "ticket_subcategories"
    __table_args__ = (
        UniqueConstraint(
            "category_id", "code", name="uq_ticket_subcategories_category_code"
        ),
    )
    category_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("ticket_categories.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    category: Mapped[TicketCategory] = relationship(back_populates="subcategories")
    services: Mapped[list[TicketService]] = relationship(back_populates="subcategory")
    tickets: Mapped[list[Ticket]] = relationship(back_populates="subcategory")


class TicketService(BaseModel):
    """Business service offered under a subcategory (for routing and SLA later)."""

    __tablename__ = "ticket_services"
    __table_args__ = (
        UniqueConstraint(
            "subcategory_id", "code", name="uq_ticket_services_subcategory_code"
        ),
    )
    subcategory_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("ticket_subcategories.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    subcategory: Mapped[TicketSubcategory] = relationship(back_populates="services")
    tickets: Mapped[list[Ticket]] = relationship(back_populates="service")


class TicketPriority(BaseModel):
    __tablename__ = "ticket_priorities"
    __table_args__ = (UniqueConstraint("code", name="uq_ticket_priorities_code"),)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str | None] = mapped_column(String(20))
    sla_minutes: Mapped[int | None] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tickets: Mapped[list[Ticket]] = relationship(back_populates="priority")


class TicketStatus(BaseModel):
    __tablename__ = "ticket_statuses"
    __table_args__ = (UniqueConstraint("code", name="uq_ticket_statuses_code"),)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str | None] = mapped_column(String(20))
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tickets: Mapped[list[Ticket]] = relationship(back_populates="status")
    transitions_from: Mapped[list[TicketStatusTransition]] = relationship(
        back_populates="from_status",
        foreign_keys="TicketStatusTransition.from_status_id",
    )
    transitions_to: Mapped[list[TicketStatusTransition]] = relationship(
        back_populates="to_status", foreign_keys="TicketStatusTransition.to_status_id"
    )


class TicketStatusTransition(BaseModel):
    """An administrator-configured, directed edge in the ticket state machine."""

    __tablename__ = "ticket_status_transitions"
    __table_args__ = (
        UniqueConstraint(
            "from_status_id", "to_status_id", name="uq_ticket_status_transitions_edge"
        ),
        Index(
            "ix_ticket_status_transitions_from_active", "from_status_id", "is_active"
        ),
    )
    from_status_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("ticket_statuses.id"), nullable=False, index=True
    )
    to_status_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("ticket_statuses.id"), nullable=False, index=True
    )
    required_permission: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    from_status: Mapped[TicketStatus] = relationship(
        back_populates="transitions_from", foreign_keys=[from_status_id]
    )
    to_status: Mapped[TicketStatus] = relationship(
        back_populates="transitions_to", foreign_keys=[to_status_id]
    )


class Ticket(BaseModel):
    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint("ticket_no", name="uq_tickets_ticket_no"),
        Index(
            "ix_tickets_requester_status_created",
            "requester_id",
            "status_id",
            "created_at",
        ),
        Index(
            "ix_tickets_assignee_status_created",
            "assigned_to",
            "status_id",
            "created_at",
        ),
        Index("ix_tickets_category_priority", "category_id", "priority_id"),
        Index(
            "ix_tickets_department_status_created",
            "department_id",
            "status_id",
            "created_at",
        ),
        Index("ix_tickets_tier_status", "current_tier", "status_id"),
    )
    ticket_no: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    requester_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    department_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("departments.id"), index=True
    )
    category_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("ticket_categories.id"), nullable=False, index=True
    )
    subcategory_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ticket_subcategories.id"), index=True
    )
    service_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ticket_services.id"), index=True
    )
    priority_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("ticket_priorities.id"), nullable=False, index=True
    )
    status_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("ticket_statuses.id"), nullable=False, index=True
    )
    assigned_to: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), index=True
    )
    source: Mapped[str] = mapped_column(String(30), default="WEB", nullable=False)
    current_tier: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    sla_breached: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # MDDR checkpoints: occurred -> detected -> diagnosed -> resolved (resolved_at below)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    diagnosed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Resolution requirement: the resolver must record what was actually done
    # to fix the issue before the ticket can transition into a resolved state.
    # Nullable at the DB layer (older rows predate this field) but the
    # /resolve endpoint must enforce it as required input.
    resolution_summary: Mapped[str | None] = mapped_column(Text)
    resolution_code: Mapped[str | None] = mapped_column(String(50))
    # Incremented by the /reopen and /reject endpoints every time a ticket
    # is sent back from a resolved/closed state, instead of being derived
    # on the fly from TicketHistory.
    reopen_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    requester: Mapped[User] = relationship(foreign_keys=[requester_id])
    assignee: Mapped[User | None] = relationship(foreign_keys=[assigned_to])

    @property
    def reporter(self) -> User:
        """API-facing alias for the ticket requester."""
        return self.requester
    department: Mapped[Department | None] = relationship(foreign_keys=[department_id])
    category: Mapped[TicketCategory] = relationship(back_populates="tickets")
    subcategory: Mapped[TicketSubcategory | None] = relationship(
        back_populates="tickets"
    )
    service: Mapped[TicketService | None] = relationship(back_populates="tickets")
    priority: Mapped[TicketPriority] = relationship(back_populates="tickets")
    status: Mapped[TicketStatus] = relationship(back_populates="tickets")
    assignments: Mapped[list[TicketAssignment]] = relationship(back_populates="ticket")
    histories: Mapped[list[TicketHistory]] = relationship(back_populates="ticket")
    comments: Mapped[list[TicketComment]] = relationship(back_populates="ticket")
    attachments: Mapped[list[TicketAttachment]] = relationship(back_populates="ticket")
    escalations: Mapped[list[TicketEscalation]] = relationship(back_populates="ticket")


class TicketNumberSequence(Base):
    """One locked counter per UTC day for human-friendly incident numbers."""

    __tablename__ = "ticket_number_sequences"
    business_date: Mapped[date] = mapped_column(Date, primary_key=True)
    last_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class TicketAssignment(BaseModel):
    __tablename__ = "ticket_assignments"
    ticket_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tickets.id"), nullable=False, index=True
    )
    assigned_from: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    assigned_to: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ticket: Mapped[Ticket] = relationship(back_populates="assignments")


class TicketEscalation(BaseModel):
    """Structured escalation history.

    Two distinct kinds share this table, distinguished by `escalation_type`:
      - FUNCTIONAL: re-routing to a more appropriate team. Tier does not
        necessarily change (e.g. Helpdesk -> Billing, both tier 1).
      - TECHNICAL: moving up the expertise chain, T1 -> T2 -> T3. Tier must
        increase.
    """

    __tablename__ = "ticket_escalations"
    __table_args__ = (
        Index("ix_ticket_escalations_ticket_escalated", "ticket_id", "escalated_at"),
        Index("ix_ticket_escalations_ticket_type", "ticket_id", "escalation_type"),
        CheckConstraint(
            "escalation_type <> 'FUNCTIONAL' OR to_department_id IS NOT NULL",
            name="ck_ticket_escalations_functional_requires_department",
        ),
        CheckConstraint(
            "escalation_type <> 'TECHNICAL' OR to_tier > from_tier",
            name="ck_ticket_escalations_technical_requires_tier_increase",
        ),
        CheckConstraint(
            "escalation_type <> 'TECHNICAL' OR "
            "(reason_code IS NOT NULL AND reason_code IN ("
            "'SKILL_REQUIRED', 'COMPLEXITY', 'ACCESS_REQUIRED', "
            "'SYSTEM_DEPENDENCY', 'UNRESOLVED_AFTER_ATTEMPTS', "
            "'SLA_RISK', 'MDDR_RISK'))",
            name="ck_ticket_escalations_technical_requires_reason",
        ),
    )
    ticket_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tickets.id"), nullable=False, index=True
    )
    escalation_type: Mapped[str] = mapped_column(String(20), nullable=False)
    from_tier: Mapped[int] = mapped_column(Integer, nullable=False)
    to_tier: Mapped[int] = mapped_column(Integer, nullable=False)
    from_department_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("departments.id")
    )
    to_department_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("departments.id")
    )
    from_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), index=True
    )
    reason_code: Mapped[str | None] = mapped_column(String(50))
    comment: Mapped[str | None] = mapped_column(Text)
    escalated_by: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    escalated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ticket: Mapped[Ticket] = relationship(back_populates="escalations")
    from_department: Mapped[Department | None] = relationship(
        foreign_keys=[from_department_id]
    )
    to_department: Mapped[Department | None] = relationship(
        foreign_keys=[to_department_id]
    )
    from_user: Mapped[User | None] = relationship(foreign_keys=[from_user_id])


class TicketHistory(BaseModel):
    __tablename__ = "ticket_histories"
    ticket_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tickets.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    field: Mapped[str | None] = mapped_column(String(100))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    performed_by: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    remark: Mapped[str | None] = mapped_column(Text)
    ticket: Mapped[Ticket] = relationship(back_populates="histories")


class TicketComment(BaseModel):
    __tablename__ = "ticket_comments"
    __table_args__ = (
        Index("ix_ticket_comments_ticket_update_type", "ticket_id", "update_type"),
    )
    ticket_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tickets.id"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # "NOTE" (general internal note) or "TECHNICAL_UPDATE" (investigation/diagnosis
    # progress entry surfaced on the T2/T3 investigation timeline).
    update_type: Mapped[str] = mapped_column(
        String(20), default="NOTE", server_default="NOTE", nullable=False
    )
    ticket: Mapped[Ticket] = relationship(back_populates="comments")
    user: Mapped[User] = relationship(foreign_keys=[user_id])
    mentions: Mapped[list[TicketCommentMention]] = relationship(
        back_populates="comment", cascade="all, delete-orphan"
    )


class TicketCommentMention(BaseModel):
    __tablename__ = "ticket_comment_mentions"
    __table_args__ = (
        UniqueConstraint(
            "comment_id", "user_id", name="uq_ticket_comment_mentions_comment_user"
        ),
    )
    comment_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("ticket_comments.id"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    comment: Mapped[TicketComment] = relationship(back_populates="mentions")


class TicketAttachment(BaseModel):
    __tablename__ = "ticket_attachments"
    ticket_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tickets.id"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False
    )
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    scan_status: Mapped[str] = mapped_column(
        String(20), default="PENDING", nullable=False, index=True
    )
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scan_detail: Mapped[str | None] = mapped_column(Text)
    ticket: Mapped[Ticket] = relationship(back_populates="attachments")


class Notification(BaseModel):
    __tablename__ = "notifications"
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ActivityLog(BaseModel):
    __tablename__ = "activity_logs"
    user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), index=True
    )
    module: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource: Mapped[str | None] = mapped_column(String(100))
    resource_id: Mapped[UUID | None] = mapped_column(Uuid)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    detail: Mapped[dict | None] = mapped_column(JSON)


class LoginHistory(BaseModel):
    __tablename__ = "login_histories"
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    ip: Mapped[str | None] = mapped_column(String(64))
    device: Mapped[str | None] = mapped_column(String(255))
    browser: Mapped[str | None] = mapped_column(String(255))
    login_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    logout_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshToken(BaseModel):
    __tablename__ = "refresh_tokens"
    session_id: Mapped[UUID] = mapped_column(
        Uuid, default=uuid4, nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    login_history_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("login_histories.id"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    jti: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    ip: Mapped[str | None] = mapped_column(String(64))
    device: Mapped[str | None] = mapped_column(String(255))
    browser: Mapped[str | None] = mapped_column(String(255))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("refresh_tokens.id")
    )
    user: Mapped[User] = relationship(
        back_populates="refresh_tokens", foreign_keys=[user_id]
    )


# --------------------------------------------------------------------------
# SLA engine
#
# Backs app/services/sla_engine.py, which was written against exactly these
# column/attribute names (timer.policy_id, timer.metric_type,
# timer.target_minutes, timer.total_paused_seconds, timer.status values
# RUNNING/PAUSED/MET/BREACHED/CANCELLED, etc.) -- see that module's docstring
# for the policy-matching / timer-lifecycle / escalation design this schema
# supports. Matches app/schemas/references/sla_policy.py + sla_escalation.py
# + the TicketSlaMetricType/TicketSlaTimerStatus enums in app/schemas/ticket.py.
#
# NOTE: app/schemas/sla_engine.py is a stale, disconnected draft with
# different field names (e.g. SLAPolicy.duration_minutes-on-target-only, no
# match_priority, timer states RUNNING/PAUSED/STOPPED) and does not match
# this table shape or app/services/sla_engine.py. Don't build against it.
# --------------------------------------------------------------------------


class SLAPolicy(BaseModel):
    """An SLA policy matched to tickets by department/category/subcategory/
    service/priority (each optional -- NULL matches any). See
    `app.services.sla_engine.match_sla_policy` for the matching algorithm.
    """

    __tablename__ = "sla_policies"
    __table_args__ = (
        UniqueConstraint("code", name="uq_sla_policies_code"),
        Index("ix_sla_policies_active_match_priority", "is_active", "match_priority"),
    )

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    department_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("departments.id"), index=True
    )
    category_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ticket_categories.id"), index=True
    )
    subcategory_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ticket_subcategories.id"), index=True
    )
    service_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ticket_services.id"), index=True
    )
    priority_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ticket_priorities.id"), index=True
    )

    match_priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    business_hours_only: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    targets: Mapped[list[SLATarget]] = relationship(back_populates="policy")
    pause_rules: Mapped[list[SLAPauseRule]] = relationship(back_populates="policy")


class SLATarget(BaseModel):
    """One RESPONSE or RESOLUTION target under a policy."""

    __tablename__ = "sla_targets"
    __table_args__ = (
        UniqueConstraint(
            "policy_id", "metric_type", name="uq_sla_targets_policy_metric"
        ),
        CheckConstraint(
            "metric_type IN ('RESPONSE', 'RESOLUTION')",
            name="ck_sla_targets_metric_type",
        ),
        CheckConstraint(
            "warning_threshold_pct BETWEEN 1 AND 100",
            name="ck_sla_targets_warning_threshold_pct",
        ),
    )

    policy_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("sla_policies.id"), nullable=False, index=True
    )
    metric_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    warning_threshold_pct: Mapped[int] = mapped_column(
        Integer, default=80, nullable=False
    )

    policy: Mapped[SLAPolicy] = relationship(back_populates="targets")


class SLAPauseRule(BaseModel):
    """Statuses that automatically pause every RUNNING timer on this policy
    while a ticket sits in them (e.g. "Awaiting Customer" pauses the clock).

    Consumed by `app.services.sla_engine.apply_status_pause_rules`, called
    after a status transition commits. A timer this table auto-pauses
    records which status did it via `TicketSlaTimer.auto_paused_status_id`
    -- only a timer paused *that* way is eligible for auto-resume when the
    ticket leaves the status; a manually-paused timer
    (`auto_paused_status_id IS NULL`) is left alone so an unrelated status
    change can't silently resume something a human paused on purpose.
    """

    __tablename__ = "sla_pause_rules"
    __table_args__ = (
        UniqueConstraint(
            "policy_id", "status_id", name="uq_sla_pause_rules_policy_status"
        ),
    )

    policy_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("sla_policies.id"), nullable=False, index=True
    )
    status_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("ticket_statuses.id"), nullable=False, index=True
    )
    reason: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    policy: Mapped[SLAPolicy] = relationship(back_populates="pause_rules")
    status: Mapped[TicketStatus] = relationship()


class TicketSlaTimer(BaseModel):
    """Live state of one RESPONSE or RESOLUTION timer for a ticket.

    `status` lifecycle: RUNNING -> (PAUSED <-> RUNNING)* -> one of
    MET / BREACHED / CANCELLED (terminal). See
    `app.services.sla_engine` pause/resume/completion functions.
    """

    __tablename__ = "ticket_sla_timers"
    __table_args__ = (
        UniqueConstraint(
            "ticket_id", "metric_type", name="uq_ticket_sla_timers_ticket_metric"
        ),
        Index("ix_ticket_sla_timers_status_due", "status", "due_at"),
        CheckConstraint(
            "metric_type IN ('RESPONSE', 'RESOLUTION')",
            name="ck_ticket_sla_timers_metric_type",
        ),
        CheckConstraint(
            "status IN ('RUNNING', 'PAUSED', 'MET', 'BREACHED', 'CANCELLED')",
            name="ck_ticket_sla_timers_status",
        ),
    )

    ticket_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tickets.id"), nullable=False, index=True
    )
    policy_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("sla_policies.id"), nullable=False, index=True
    )
    metric_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="RUNNING", nullable=False
    )

    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_paused_seconds: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    # Set only when SLAPauseRule auto-paused this timer; records which
    # status is holding it paused so apply_status_pause_rules knows it's
    # safe to auto-resume once the ticket leaves that status. NULL for a
    # manual pause_sla_timer() call -- see SLAPauseRule docstring.
    auto_paused_status_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ticket_statuses.id")
    )

    met_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    breached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    ticket: Mapped[Ticket] = relationship()
    policy: Mapped[SLAPolicy] = relationship()


class SLAEscalationTrigger(BaseModel):
    """Fires when a timer on `policy_id` crosses its WARNING threshold
    (SLATarget.warning_threshold_pct) or its BREACH point. NULL metric_type
    applies to both RESPONSE and RESOLUTION targets.
    """

    __tablename__ = "sla_escalation_triggers"
    __table_args__ = (
        Index(
            "ix_sla_escalation_triggers_policy_trigger_on",
            "policy_id",
            "trigger_on",
        ),
        CheckConstraint(
            "trigger_on IN ('WARNING', 'BREACH')",
            name="ck_sla_escalation_triggers_trigger_on",
        ),
        CheckConstraint(
            "metric_type IS NULL OR metric_type IN ('RESPONSE', 'RESOLUTION')",
            name="ck_sla_escalation_triggers_metric_type",
        ),
    )

    policy_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("sla_policies.id"), nullable=False, index=True
    )
    trigger_on: Mapped[str] = mapped_column(String(20), nullable=False)
    metric_type: Mapped[str | None] = mapped_column(String(20))

    escalate_to_department_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("departments.id")
    )
    escalate_to_tier: Mapped[int | None] = mapped_column(Integer)
    notify_user_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    notify_role_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    channels: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    policy: Mapped[SLAPolicy] = relationship()


class SLAEscalationEvent(BaseModel):
    """One row per trigger firing on a specific timer -- lets
    `evaluate_escalations` check "already fired?" without re-deriving it
    from TicketHistory text, and guarantees a trigger fires at most once
    per timer.
    """

    __tablename__ = "sla_escalation_events"
    __table_args__ = (
        UniqueConstraint(
            "trigger_id", "timer_id", name="uq_sla_escalation_events_trigger_timer"
        ),
    )

    trigger_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("sla_escalation_triggers.id"), nullable=False, index=True
    )
    timer_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("ticket_sla_timers.id"), nullable=False, index=True
    )
    ticket_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tickets.id"), nullable=False, index=True
    )
    trigger_on: Mapped[str] = mapped_column(String(20), nullable=False)
    fired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    trigger: Mapped[SLAEscalationTrigger] = relationship()
    timer: Mapped[TicketSlaTimer] = relationship()

# ==========================================================
# Knowledge Base
# ==========================================================


class KBArticleStatus(BaseModel):
    """Configurable publishing-workflow state for KB articles, mirroring
    TicketStatus so administrators can adapt the workflow without a
    deployment."""

    __tablename__ = "kb_article_statuses"
    __table_args__ = (UniqueConstraint("code", name="uq_kb_article_statuses_code"),)

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str | None] = mapped_column(String(20))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    articles: Mapped[list[KBArticle]] = relationship(back_populates="status")
    transitions_from: Mapped[list[KBArticleStatusTransition]] = relationship(
        back_populates="from_status",
        foreign_keys="KBArticleStatusTransition.from_status_id",
    )
    transitions_to: Mapped[list[KBArticleStatusTransition]] = relationship(
        back_populates="to_status",
        foreign_keys="KBArticleStatusTransition.to_status_id",
    )


class KBArticleStatusTransition(BaseModel):
    """An administrator-configured, directed edge in the KB article
    publishing state machine."""

    __tablename__ = "kb_article_status_transitions"
    __table_args__ = (
        UniqueConstraint(
            "from_status_id", "to_status_id", name="uq_kb_article_status_transitions_edge"
        ),
        Index(
            "ix_kb_article_status_transitions_from_active", "from_status_id", "is_active"
        ),
    )

    from_status_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("kb_article_statuses.id"), nullable=False, index=True
    )
    to_status_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("kb_article_statuses.id"), nullable=False, index=True
    )
    required_permission: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    from_status: Mapped[KBArticleStatus] = relationship(
        back_populates="transitions_from", foreign_keys=[from_status_id]
    )
    to_status: Mapped[KBArticleStatus] = relationship(
        back_populates="transitions_to", foreign_keys=[to_status_id]
    )


class KBCategory(BaseModel):
    """Self-referential KB category tree, mirroring Department."""

    __tablename__ = "kb_categories"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("kb_categories.id")
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    parent: Mapped[KBCategory | None] = relationship(
        remote_side="KBCategory.id", back_populates="children"
    )
    children: Mapped[list[KBCategory]] = relationship(back_populates="parent")
    articles: Mapped[list[KBArticle]] = relationship(back_populates="category")


class KBArticle(BaseModel):
    __tablename__ = "kb_articles"
    __table_args__ = (
        Index("ix_kb_articles_status_category", "status_id", "category_id"),
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("kb_categories.id"), nullable=False, index=True
    )
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("kb_article_statuses.id"), nullable=False, index=True
    )
    current_version_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    author_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    category: Mapped[KBCategory] = relationship(back_populates="articles")
    status: Mapped[KBArticleStatus] = relationship(back_populates="articles")
    author: Mapped[User] = relationship(foreign_keys=[author_id])
    versions: Mapped[list[KBArticleVersion]] = relationship(
        back_populates="article", foreign_keys="KBArticleVersion.article_id"
    )
    incident_links: Mapped[list[KBArticleIncidentLink]] = relationship(
        back_populates="article", foreign_keys="KBArticleIncidentLink.article_id"
    )


class KBArticleVersion(BaseModel):
    """A snapshot taken at submit-for-review and at publish time (not on
    every plain edit) -- see app/services/knowledge_base.py."""

    __tablename__ = "kb_article_versions"
    __table_args__ = (
        UniqueConstraint("article_id", "version_no", name="uq_kb_article_versions_article_no"),
    )

    article_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("kb_articles.id"), nullable=False, index=True
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    change_summary: Mapped[str | None] = mapped_column(String(500))
    changed_by_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False
    )

    article: Mapped[KBArticle] = relationship(
        back_populates="versions", foreign_keys=[article_id]
    )
    changed_by: Mapped[User] = relationship(foreign_keys=[changed_by_id])


class KBArticleIncidentLink(BaseModel):
    """Join table linking a KB article to a ticket (incident)."""

    __tablename__ = "kb_article_incident_links"
    __table_args__ = (
        UniqueConstraint(
            "article_id", "ticket_id", name="uq_kb_article_incident_links_article_ticket"
        ),
    )

    article_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("kb_articles.id"), nullable=False, index=True
    )
    ticket_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tickets.id"), nullable=False, index=True
    )
    note: Mapped[str | None] = mapped_column(String(500))
    linked_by_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False
    )
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    article: Mapped[KBArticle] = relationship(
        back_populates="incident_links", foreign_keys=[article_id]
    )
    ticket: Mapped[Ticket] = relationship(foreign_keys=[ticket_id])
    linked_by: Mapped[User] = relationship(foreign_keys=[linked_by_id])


# ==========================================================
# Notification Engine
# ==========================================================


class NotificationRule(BaseModel):
    """Config-level rule: 'when `event_type` happens, notify these
    recipients on these channels'. `channels`/`recipient_role_ids`/
    `recipient_user_ids` are JSON lists (channel codes / role or user UUID
    strings) rather than join tables, mirroring `SLAEscalationTrigger`'s
    `notify_user_ids`/`notify_role_ids`/`channels` columns.

    `template_id` is a forward-looking, unenforced reference: there is no
    NotificationTemplate table yet, so it is stored but not validated or
    used for rendering.
    """

    __tablename__ = "notification_rules"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    channels: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    recipient_role_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    recipient_user_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    template_id: Mapped[UUID | None] = mapped_column(Uuid)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class EscalationNotification(BaseModel):
    """One row per (ticket, escalation trigger, channel) dispatch attempt
    fired by the SLA engine's escalation sweep -- see
    app/services/notification_engine.py:dispatch_escalation and
    app/services/async_sla.py:run_scheduler_tick."""

    __tablename__ = "escalation_notifications"

    ticket_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tickets.id"), nullable=False, index=True
    )
    escalation_trigger_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("sla_escalation_triggers.id"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    recipient_user_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    message: Mapped[str] = mapped_column(String(2000), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    ticket: Mapped[Ticket] = relationship()
    escalation_trigger: Mapped[SLAEscalationTrigger] = relationship()


class NotificationHistory(BaseModel):
    """Delivery log: one row per attempted delivery on a channel to a single
    recipient, covering both regular `NotificationRule`-driven dispatches
    and `EscalationNotification` dispatches. At most one of
    `notification_id` / `escalation_notification_id` is set -- escalation
    dispatch always sets `escalation_notification_id`; a rule-driven
    dispatch sets `notification_id` only for the in-app channel (where an
    actual `Notification` row was written) and leaves both NULL for other
    channels (email/SMS/websocket), which have no per-delivery parent
    record of their own."""

    __tablename__ = "notification_history"
    __table_args__ = (
        CheckConstraint(
            "NOT (notification_id IS NOT NULL AND escalation_notification_id IS NOT NULL)",
            name="ck_notification_history_not_both_sources",
        ),
    )

    notification_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("notifications.id"), index=True
    )
    escalation_notification_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("escalation_notifications.id"), index=True
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    recipient_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(1000))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    notification: Mapped[Notification | None] = relationship()
    escalation_notification: Mapped[EscalationNotification | None] = relationship()
    recipient: Mapped[User] = relationship(foreign_keys=[recipient_user_id])


# ==========================================================
# Root Cause Analysis
# ==========================================================
# An RCA is anchored to either a ticket (incident-level RCA) or a problem
# (problem-level RCA covering multiple related incidents) -- mirrors the
# ticket_id/problem_id anchor already declared on app.schemas.rca.
#
# `problem_id` columns below are plain UUIDs with no FK yet: the
# `problems` table doesn't exist until the Problem Management migration
# lands. That migration adds the FK via `op.create_foreign_key` rather than
# recreating these tables -- see its docstring.


class RootCause(BaseModel):
    """The identified root cause of an incident or problem. Contributing
    factors, impact analysis, and the RCA report all hang off this."""

    __tablename__ = "root_causes"
    __table_args__ = (
        CheckConstraint(
            "ticket_id IS NOT NULL OR problem_id IS NOT NULL",
            name="ck_root_causes_anchor",
        ),
        Index("ix_root_causes_ticket_id", "ticket_id"),
        Index("ix_root_causes_problem_id", "problem_id"),
    )

    ticket_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("tickets.id"), nullable=True
    )
    problem_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    identified_by_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )

    ticket: Mapped[Ticket | None] = relationship()
    identified_by: Mapped[User] = relationship(foreign_keys=[identified_by_id])
    contributing_factors: Mapped[list[ContributingFactor]] = relationship(
        back_populates="root_cause"
    )
    impact_analyses: Mapped[list[ImpactAnalysis]] = relationship(
        back_populates="root_cause"
    )
    rca_reports: Mapped[list[RCAReport]] = relationship(back_populates="root_cause")


class ContributingFactor(BaseModel):
    __tablename__ = "contributing_factors"

    root_cause_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("root_causes.id"), nullable=False, index=True
    )
    factor_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False)

    root_cause: Mapped[RootCause] = relationship(back_populates="contributing_factors")


class ImpactAnalysis(BaseModel):
    __tablename__ = "impact_analyses"
    __table_args__ = (
        CheckConstraint(
            "business_impact IN ('NONE', 'LOW', 'MEDIUM', 'HIGH', 'SEVERE')",
            name="ck_impact_analyses_business_impact",
        ),
    )

    root_cause_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("root_causes.id"), nullable=False, index=True
    )
    affected_service_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    affected_users_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    downtime_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    business_impact: Mapped[str] = mapped_column(
        String(20), default="LOW", nullable=False
    )
    financial_impact: Mapped[float | None] = mapped_column(Numeric(14, 2))
    notes: Mapped[str | None] = mapped_column(String(2000))

    root_cause: Mapped[RootCause] = relationship(back_populates="impact_analyses")


class RCAReport(BaseModel):
    """The written postmortem artifact. `status` is a plain, fixed
    three-value workflow (DRAFT -> IN_REVIEW -> APPROVED, or IN_REVIEW ->
    DRAFT on rejection) -- unlike TicketStatus/KBArticleStatus this isn't
    configurable master data, matching the fixed `RCAReportStatus` enum
    already declared in app.schemas.rca."""

    __tablename__ = "rca_reports"
    __table_args__ = (
        CheckConstraint(
            "ticket_id IS NOT NULL OR problem_id IS NOT NULL",
            name="ck_rca_reports_anchor",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'IN_REVIEW', 'APPROVED')",
            name="ck_rca_reports_status",
        ),
        Index("ix_rca_reports_ticket_id", "ticket_id"),
        Index("ix_rca_reports_problem_id", "problem_id"),
    )

    ticket_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("tickets.id"), nullable=True
    )
    problem_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    root_cause_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("root_causes.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    timeline: Mapped[str | None] = mapped_column(Text)
    corrective_actions: Mapped[str | None] = mapped_column(String(4000))
    preventive_actions: Mapped[str | None] = mapped_column(String(4000))
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False)

    prepared_by_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    approved_by_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    ticket: Mapped[Ticket | None] = relationship()
    root_cause: Mapped[RootCause] = relationship(back_populates="rca_reports")
    prepared_by: Mapped[User] = relationship(foreign_keys=[prepared_by_id])
    approved_by: Mapped[User | None] = relationship(foreign_keys=[approved_by_id])
