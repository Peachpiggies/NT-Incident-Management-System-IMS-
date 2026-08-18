import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.analytics import router as analytics_router
from app.api.v1.attachments import router as attachments_router
from app.api.v1.auth import router as auth_router
from app.api.v1.categories import router as categories_router
from app.api.v1.change import router as change_router
from app.api.v1.health import router as health_router
from app.api.v1.knowledge_base import router as knowledge_base_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.organization import router as organization_router
from app.api.v1.permissions import router as permissions_router
from app.api.v1.problem import router as problem_router
from app.api.v1.rca import router as rca_router
from app.api.v1.references import router as references_router
from app.api.v1.realtime import router as realtime_router
from app.api.v1.sla import router as sla_router
from app.api.v1.tickets import router as tickets_router
from app.api.v1.users import router as users_router
from app.api.v1.workflow import router as workflow_router
from app.core.config import settings
from app.db.session import AsyncSessionLocal, engine
from app.services.async_sla import run_scheduler_tick

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


async def _sla_scheduler() -> None:
    """Continuously evaluate running SLA timers in the live application."""
    interval = max(5, int(getattr(settings, "sla_scheduler_interval_seconds", 60)))
    while True:
        try:
            async with AsyncSessionLocal() as db:
                breached, escalated = await run_scheduler_tick(db)
                if breached or escalated:
                    logger.info(
                        "SLA scheduler: breached=%s escalations=%s",
                        breached,
                        escalated,
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("SLA scheduler tick failed")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Starting %s in %s", settings.app_name, settings.environment)
    scheduler_task = (
        asyncio.create_task(_sla_scheduler())
        if settings.sla_scheduler_enabled
        else None
    )
    try:
        yield
    finally:
        if scheduler_task is not None:
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass
        await engine.dispose()
        logger.info("Stopped %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description="""
NT Incident Management System API.

All resource identifiers are UUIDs. Authorization is database-driven PBAC:
each protected operation names its required permission (for example
`ticket.assign` or `department.manage`). Ticket visibility additionally uses
`ticket.read_own` or `ticket.read_all`.

Authenticate with `POST /api/v1/auth/login`, then use the returned access token
with the **Authorize** button. Refresh tokens are only accepted by the auth
session endpoints and are never returned by session-listing APIs.
""",
    openapi_tags=[
        {
            "name": "Auth",
            "description": "JWT authentication and refresh-token session management.",
        },
        {
            "name": "Users",
            "description": "UUID user profiles and multi-role management.",
        },
        {
            "name": "Organization",
            "description": "Departments, roles, and user-role assignments.",
        },
        {
            "name": "Permissions",
            "description": "PBAC permissions and role-permission assignments.",
        },
        {
            "name": "Tickets",
            "description": "UUID tickets, classification, workflow and department/user assignment. List responses are paginated.",
        },
        {
            "name": "Change Management",
            "description": "Change requests, risk assessment, approval quorum, implementation, validation, rollback, and closure.",
        },
        {
            "name": "Categories",
            "description": "Configurable Category → Subcategory → Service master data for ticket classification.",
        },
        {
            "name": "Workflow",
            "description": "Configuration of allowed ticket-status transitions.",
        },
        {
            "name": "Dashboard & Analytics",
            "description": "Executive, manager, helpdesk, and customer dashboards, operational metrics, reports, and CSV exports.",
        },
        {
            "name": "SLA",
            "description": "SLA policy configuration, live timers, pause/resume, and timer evaluation.",
        },
        {
            "name": "Attachments",
            "description": "Secure JPG, PNG, PDF, DOCX, and XLSX ticket attachments.",
        },
        {
            "name": "Knowledge Base",
            "description": "KB categories, articles, versioning, the publishing workflow, and article-incident linking.",
        },
        {
            "name": "Realtime",
            "description": "WebSocket channel for realtime notification delivery.",
        },
    ],
    openapi_url="/api/v1/openapi.json",
    docs_url="/docs",
    swagger_ui_parameters={"persistAuthorization": True},
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router, prefix="/api/v1/auth")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(categories_router, prefix="/api/v1")
app.include_router(change_router, prefix="/api/v1")
app.include_router(attachments_router, prefix="/api/v1")
app.include_router(notifications_router, prefix="/api/v1")
app.include_router(organization_router, prefix="/api/v1")
app.include_router(permissions_router, prefix="/api/v1")
app.include_router(realtime_router, prefix="/api/v1")
app.include_router(sla_router, prefix="/api/v1")
app.include_router(tickets_router, prefix="/api/v1")
app.include_router(knowledge_base_router, prefix="/api/v1")
app.include_router(rca_router, prefix="/api/v1")
app.include_router(problem_router, prefix="/api/v1")
app.include_router(references_router, prefix="/api/v1")
app.include_router(workflow_router, prefix="/api/v1")
app.include_router(health_router, prefix="/api/v1")
