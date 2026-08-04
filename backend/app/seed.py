import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.models import Category, User
from app.db.session import AsyncSessionLocal
from app.domain import Role

DEFAULT_CATEGORIES = [
    ("Software", "Software incidents and defects"),
    ("Network", "Network outages and connectivity issues"),
    ("Hardware", "Hardware failures and maintenance"),
    ("Access", "Access requests and privilege issues"),
]

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "ChangeMe123!"
ADMIN_FULL_NAME = "IMS Administrator"


async def seed_database() -> None:
    async with AsyncSessionLocal() as session:
        for name, description in DEFAULT_CATEGORIES:
            existing = await session.execute(select(Category).where(Category.name == name))
            if not existing.scalar_one_or_none():
                session.add(Category(name=name, description=description, is_active=True))

        admin_result = await session.execute(select(User).where(User.email == ADMIN_EMAIL))
        if not admin_result.scalar_one_or_none():
            session.add(
                User(
                    email=ADMIN_EMAIL,
                    full_name=ADMIN_FULL_NAME,
                    password_hash=hash_password(ADMIN_PASSWORD),
                    role=Role.MANAGER,
                    is_active=True,
                )
            )

        await session.commit()

    print("Seed complete")
    print(f"Admin user: {ADMIN_EMAIL}")
    print(f"Admin password: {ADMIN_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(seed_database())
