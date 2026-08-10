import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.attachments import router as attachments_router
from app.api.v1.auth import router as auth_router
from app.api.v1.categories import router as categories_router
from app.api.v1.health import router as health_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.organization import router as organization_router
from app.api.v1.permissions import router as permissions_router
from app.api.v1.tickets import router as tickets_router
from app.api.v1.users import router as users_router
from app.api.v1.workflow import router as workflow_router
from app.core.config import settings
from app.db.session import engine

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Starting %s in %s", settings.app_name, settings.environment)
    yield
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
            "name": "Categories",
            "description": "Configurable Category → Subcategory → Service master data for ticket classification.",
        },
        {
            "name": "Workflow",
            "description": "Configuration of allowed ticket-status transitions.",
        },
        {
            "name": "Attachments",
            "description": "Secure JPG, PNG, PDF, DOCX, and XLSX ticket attachments.",
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
app.include_router(users_router, prefix="/api/v1")
app.include_router(categories_router, prefix="/api/v1")
app.include_router(attachments_router, prefix="/api/v1")
app.include_router(notifications_router, prefix="/api/v1")
app.include_router(organization_router, prefix="/api/v1")
app.include_router(permissions_router, prefix="/api/v1")
app.include_router(tickets_router, prefix="/api/v1")
app.include_router(workflow_router, prefix="/api/v1")
app.include_router(health_router, prefix="/api/v1")
