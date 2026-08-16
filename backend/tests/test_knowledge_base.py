"""HTTP-level contract for the Knowledge Base: categories, articles,
the publishing workflow (submit -> review -> publish / reject -> archive ->
restore), version snapshotting, and article <-> incident linking."""

import asyncio
from dataclasses import dataclass

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.v1.dependencies import get_db
from app.core.security import hash_password
from app.db.models import (
    Base,
    Department,
    KBArticleStatus,
    KBArticleStatusTransition,
    Permission,
    Role,
    RolePermission,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
)
from app.main import app

PASSWORD = "Secure-password-123!"


@dataclass
class Seed:
    author: User
    reviewer: User
    other_author: User


async def _create_harness(tmp_path) -> tuple[object, async_sessionmaker[AsyncSession], Seed]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'kb.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with sessions() as db:
        author_role = Role(code="author", name="Author", is_system=True)
        reviewer_role = Role(code="reviewer", name="Reviewer", is_system=True)

        permissions = [
            Permission(module="kb", action=action, code=f"kb.{action}")
            for action in [
                "create",
                "update",
                "delete",
                "submit",
                "review",
                "archive",
                "restore",
                "link_incident",
            ]
        ]

        department = Department(code="OPS", name="Operations")

        author = User(
            username="kb-author",
            email="kb-author@example.com",
            first_name="Author",
            last_name="One",
            password_hash=hash_password(PASSWORD),
            department=department,
        )
        other_author = User(
            username="kb-author-2",
            email="kb-author-2@example.com",
            first_name="Author",
            last_name="Two",
            password_hash=hash_password(PASSWORD),
            department=department,
        )
        reviewer = User(
            username="kb-reviewer",
            email="kb-reviewer@example.com",
            first_name="Reviewer",
            last_name="One",
            password_hash=hash_password(PASSWORD),
            department=department,
        )

        db.add_all(
            [
                author_role,
                reviewer_role,
                *permissions,
                department,
                author,
                other_author,
                reviewer,
            ]
        )
        await db.flush()

        db.add_all(
            [
                UserRole(user_id=author.id, role_id=author_role.id),
                UserRole(user_id=other_author.id, role_id=author_role.id),
                UserRole(user_id=reviewer.id, role_id=reviewer_role.id),
            ]
        )
        by_code = {p.code: p for p in permissions}
        for code in ("kb.create", "kb.update", "kb.submit", "kb.link_incident"):
            db.add(RolePermission(role_id=author_role.id, permission_id=by_code[code].id))
        for code in ("kb.review", "kb.archive", "kb.restore", "kb.delete"):
            db.add(RolePermission(role_id=reviewer_role.id, permission_id=by_code[code].id))

        statuses = {
            code: KBArticleStatus(code=code, name=code.title(), is_active=True)
            for code in ["DRAFT", "IN_REVIEW", "PUBLISHED", "ARCHIVED"]
        }
        db.add_all(statuses.values())
        await db.flush()

        for from_code, to_code, permission_code in [
            ("DRAFT", "IN_REVIEW", "kb.submit"),
            ("IN_REVIEW", "PUBLISHED", "kb.review"),
            ("IN_REVIEW", "DRAFT", "kb.review"),
            ("PUBLISHED", "ARCHIVED", "kb.archive"),
            ("ARCHIVED", "DRAFT", "kb.restore"),
        ]:
            db.add(
                KBArticleStatusTransition(
                    from_status_id=statuses[from_code].id,
                    to_status_id=statuses[to_code].id,
                    required_permission=permission_code,
                )
            )

        await db.commit()
        return engine, sessions, Seed(author, reviewer, other_author)


def _token(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_kb_publishing_workflow_and_incident_linking(tmp_path) -> None:
    engine, sessions, seed = asyncio.run(_create_harness(tmp_path))

    async def override_get_db():
        async with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            author_token = _token(client, seed.author.email)
            other_author_token = _token(client, seed.other_author.email)
            reviewer_token = _token(client, seed.reviewer.email)

            # Category
            category = client.post(
                "/api/v1/kb/categories",
                headers=_headers(author_token),
                json={"name": "Network"},
            )
            assert category.status_code == 201, category.text
            category_id = category.json()["id"]

            # Create article -> DRAFT
            article = client.post(
                "/api/v1/kb/articles",
                headers=_headers(author_token),
                json={
                    "title": "How to reset your VPN client",
                    "summary": "Quick steps to fix VPN connectivity",
                    "content": "Step one: restart the client. Step two: reconnect.",
                    "category_id": category_id,
                    "tags": ["vpn", "network"],
                },
            )
            assert article.status_code == 201, article.text
            article_id = article.json()["id"]
            assert article.json()["status"]["code"] == "DRAFT"
            assert article.json()["current_version_no"] == 0

            # A different author cannot see this draft
            assert (
                client.get(
                    f"/api/v1/kb/articles/{article_id}", headers=_headers(other_author_token)
                ).status_code
                == 404
            )

            # Plain edit stays a draft, does not bump the version
            edited = client.put(
                f"/api/v1/kb/articles/{article_id}",
                headers=_headers(author_token),
                json={"content": "Step one: restart the client fully. Step two: reconnect."},
            )
            assert edited.status_code == 200, edited.text
            assert edited.json()["current_version_no"] == 0

            # Submit for review -> snapshots v1
            submitted = client.post(
                f"/api/v1/kb/articles/{article_id}/submit",
                headers=_headers(author_token),
                json={"note": "Ready for review"},
            )
            assert submitted.status_code == 200, submitted.text
            assert submitted.json()["status"]["code"] == "IN_REVIEW"

            versions = client.get(
                f"/api/v1/kb/articles/{article_id}/versions", headers=_headers(author_token)
            )
            assert versions.status_code == 200
            assert versions.json()["total"] == 1
            assert versions.json()["items"][0]["version_no"] == 1

            # Reviewer sends it back to draft (reject) -- no new version
            rejected = client.post(
                f"/api/v1/kb/articles/{article_id}/review",
                headers=_headers(reviewer_token),
                json={"approve": False, "comment": "Needs more detail"},
            )
            assert rejected.status_code == 200, rejected.text
            assert rejected.json()["status"]["code"] == "DRAFT"

            # Resubmit -> snapshots v2
            resubmitted = client.post(
                f"/api/v1/kb/articles/{article_id}/submit",
                headers=_headers(author_token),
                json={},
            )
            assert resubmitted.status_code == 200

            # Reviewer approves -> PUBLISHED, snapshots v3
            published = client.post(
                f"/api/v1/kb/articles/{article_id}/review",
                headers=_headers(reviewer_token),
                json={"approve": True},
            )
            assert published.status_code == 200, published.text
            assert published.json()["status"]["code"] == "PUBLISHED"
            assert published.json()["published_at"] is not None

            versions_after_publish = client.get(
                f"/api/v1/kb/articles/{article_id}/versions", headers=_headers(author_token)
            )
            assert versions_after_publish.json()["total"] == 3
            assert {v["version_no"] for v in versions_after_publish.json()["items"]} == {1, 2, 3}

            # Now anyone can read the published article, and view_count increments
            first_read = client.get(
                f"/api/v1/kb/articles/{article_id}", headers=_headers(other_author_token)
            )
            assert first_read.status_code == 200
            assert first_read.json()["view_count"] == 1
            second_read = client.get(
                f"/api/v1/kb/articles/{article_id}", headers=_headers(other_author_token)
            )
            assert second_read.json()["view_count"] == 2

            # Illegal transition: PUBLISHED -> IN_REVIEW is not configured
            illegal = client.post(
                f"/api/v1/kb/articles/{article_id}/submit",
                headers=_headers(author_token),
                json={},
            )
            assert illegal.status_code == 409

            # Article <-> Incident linking requires a real ticket; build minimal
            # fixtures for one via a direct DB insert (ticket creation flow is
            # covered by tests/test_ticket_lifecycle.py already).
            async def _make_ticket():
                from app.db.models import Ticket

                async with sessions() as db:
                    status_row = TicketStatus(code="NEW", name="New", is_active=True)
                    ticket_category = TicketCategory(code="NET", name="Network", is_active=True)
                    priority = TicketPriority(code="HIGH", name="High", is_active=True)
                    db.add_all([status_row, ticket_category, priority])
                    await db.flush()
                    ticket = Ticket(
                        ticket_no="INC-0001",
                        title="VPN outage",
                        description="VPN is down",
                        category_id=ticket_category.id,
                        priority_id=priority.id,
                        status_id=status_row.id,
                        requester_id=seed.author.id,
                    )
                    db.add(ticket)
                    await db.commit()
                    await db.refresh(ticket)
                    return ticket.id

            ticket_id = asyncio.run(_make_ticket())

            link = client.post(
                f"/api/v1/kb/articles/{article_id}/incidents",
                headers=_headers(author_token),
                json={"article_id": article_id, "ticket_id": str(ticket_id), "note": "Root cause"},
            )
            assert link.status_code == 201, link.text

            # Duplicate link rejected
            dup = client.post(
                f"/api/v1/kb/articles/{article_id}/incidents",
                headers=_headers(author_token),
                json={"article_id": article_id, "ticket_id": str(ticket_id)},
            )
            assert dup.status_code == 409

            from_ticket = client.get(
                f"/api/v1/tickets/{ticket_id}/kb-articles", headers=_headers(author_token)
            )
            assert from_ticket.status_code == 200
            assert from_ticket.json()["total"] == 1
            assert from_ticket.json()["items"][0]["article"]["id"] == article_id

            unlink = client.delete(
                f"/api/v1/kb/articles/{article_id}/incidents/{ticket_id}",
                headers=_headers(author_token),
            )
            assert unlink.status_code == 204

            # Archive -> restore cycle
            archived = client.post(
                f"/api/v1/kb/articles/{article_id}/archive",
                headers=_headers(reviewer_token),
                json={"reason": "Superseded"},
            )
            assert archived.status_code == 200
            assert archived.json()["status"]["code"] == "ARCHIVED"

            restored = client.post(
                f"/api/v1/kb/articles/{article_id}/restore",
                headers=_headers(reviewer_token),
                json={"reason": "Bring back for edits"},
            )
            assert restored.status_code == 200
            assert restored.json()["status"]["code"] == "DRAFT"
            assert restored.json()["published_at"] is None
    finally:
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())
