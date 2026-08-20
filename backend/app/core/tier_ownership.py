"""Tier-ownership check shared by anything that lets a user act on a ticket
because of *which team currently holds it* (escalating further, receiving
an escalated ticket), as opposed to a flat RBAC permission check.

`require_permission(...)` (see core/permissions.py) only answers "does this
user's role carry this permission code at all" -- it says nothing about
whether the user is the team the ticket is actually sitting with right now.
Several endpoints (`/escalate/technical`, `/escalate/functional`,
`/receive_escalated`) were only gated by the flat permission, which meant
e.g. a Helpdesk T1 user could escalate a ticket already at T2, or a Helpdesk
T2 user could `receive_escalated` a ticket that had moved on to Tier 3
(Manager) -- because their role still carried the endpoint's permission
code even though they weren't the current tier holder. This module is the
one place that tier-ownership rule lives, so it can't drift between call
sites.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Role, Ticket, User, UserRole

MAX_TIER = 3

# Mirrors the frontend's currentStepFromTicket() (tickets/[id]/page.tsx):
# tier 1 -> helpdesk_t1, tier 2 -> helpdesk_t2, tier 3 and above -> manager
# (there's no dedicated tier-3 role in this backend).
TIER_ROLE_CODE = {1: "helpdesk_t1", 2: "helpdesk_t2", 3: "manager"}


async def require_current_tier_holder(db: AsyncSession, ticket: Ticket, actor: User) -> None:
    """Raise 403 unless `actor` holds the role for `ticket.current_tier`.

    `admin` is exempt -- system administrators can act on any ticket
    regardless of tier.
    """
    role_codes = set(
        (
            await db.execute(
                select(Role.code)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(
                    UserRole.user_id == actor.id,
                    UserRole.is_deleted.is_(False),
                    Role.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    if "admin" in role_codes:
        return
    required_role = TIER_ROLE_CODE.get(min(ticket.current_tier, MAX_TIER))
    if required_role not in role_codes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Only the team currently holding this ticket "
                f"(tier {ticket.current_tier}) or an admin can do this"
            ),
        )
