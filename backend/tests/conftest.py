import os

# Set test defaults only if not already provided in the environment.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("JWT_SECRET", "testsecret")
