"""Resolve a user's effective permission codes via Role -> RolePermission -> Permission.

This is deliberately small: it turns the RBAC tables already in models.py into
a `Callable[[str], bool]` that `ticket_workflow.transition_status(...)`
expects for its `has_permission` argument. It does not touch authentication
(who the user is) -- only authorization (what they're allowed to do), and
assumes a `get_current_user` dependency already exists elsewhere that
resolves the JWT/refresh-token flow implied by `RefreshToken`/`LoginHistory`.
"""

from __future__ import annotations

from typing import Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Permission, RolePermission, UserRole


def get_user_permission_codes(session: Session, user_id: UUID) -> set[str]:
    """All permission codes granted to a user through any active role."""
    rows = session.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(
            UserRole.user_id == user_id,
            UserRole.is_deleted.is_(False),
            RolePermission.is_deleted.is_(False),
            Permission.is_deleted.is_(False),
        )
    ).scalars().all()
    return set(rows)


def make_permission_checker(session: Session, user_id: UUID) -> Callable[[str], bool]:
    """Build a cached `has_permission(code) -> bool` closure for one request.

    Resolves the user's permission codes once, then reuses that set for every
    check within the same request -- avoids re-querying on every
    `transition_status` call inside a workflow that might chain several.
    """
    codes = get_user_permission_codes(session, user_id)

    def has_permission(code: str) -> bool:
        return code in codes

    return has_permission


def require_permission(session: Session, user_id: UUID, code: str) -> None:
    """Raise PermissionError if the user lacks `code`. Convenience for
    call sites that only need a single one-off check.
    """
    if code not in get_user_permission_codes(session, user_id):
        raise PermissionError(f"Missing required permission: {code}")