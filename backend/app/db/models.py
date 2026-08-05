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
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
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
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requester: Mapped[User] = relationship(foreign_keys=[requester_id])
    assignee: Mapped[User | None] = relationship(foreign_keys=[assigned_to])
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
    ticket_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tickets.id"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ticket: Mapped[Ticket] = relationship(back_populates="comments")
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
