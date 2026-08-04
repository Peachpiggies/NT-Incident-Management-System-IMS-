from fastapi import APIRouter

from app.domain import Role

router = APIRouter(tags=["Permissions"])

PERMISSIONS = {
    Role.CUSTOMER.value: [
        "ticket:create",
        "ticket:read_own",
        "ticket:comment_own",
    ],
    Role.TIER1.value: [
        "ticket:view_queue",
        "ticket:assign",
        "ticket:resolve",
        "ticket:escalate",
    ],
    Role.TIER2.value: [
        "ticket:receive_escalated",
        "ticket:resolve",
        "ticket:internal_note",
        "ticket:close",
        "ticket:reopen",
    ],
    Role.MANAGER.value: [
        "dashboard:view",
        "report:view",
        "user:manage",
        "role:manage",
        "ticket:view_all",
    ],
}


@router.get("/permissions")
async def list_permissions() -> dict[str, list[str]]:
    return PERMISSIONS
