from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.service import create_access_token
from app.main import app
from app.models.user import User

TENANT_A_ID: UUID = uuid4()
TENANT_B_ID: UUID = uuid4()


# ── Test DB ─────────────────────────────────────────────────────────────────
# Points to the revops_test database (see root conftest.py for env setup).
_TEST_DB_URL = "postgresql+asyncpg://revops:revops@localhost:5433/revops_test"


@pytest_asyncio.fixture
async def test_db() -> AsyncGenerator[AsyncSession, None]:
    """Real async DB session against revops_test with automatic rollback.

    Each test gets an isolated session; uncommitted writes are rolled back
    on teardown so tests do not pollute each other.
    """
    # Create a fresh engine per test to avoid event loop mismatch issues
    engine = create_async_engine(_TEST_DB_URL, future=True, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
            await session.close()
    await engine.dispose()


def make_user(tenant_id: UUID, email: str = "user@test.com") -> User:
    """Crée un User mock sans DB."""
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.email = email
    user.tenant_id = tenant_id
    user.is_active = True
    user.full_name = "Test User"
    user.created_at = datetime.now(timezone.utc)
    return user  # type: ignore[return-value]


@pytest.fixture
def user_tenant_a() -> User:
    return make_user(TENANT_A_ID, "user_a@test.com")


@pytest.fixture
def user_tenant_b() -> User:
    return make_user(TENANT_B_ID, "user_b@test.com")


@pytest.fixture
def access_token_tenant_a(user_tenant_a: User) -> str:
    return create_access_token(user_tenant_a)


@pytest.fixture
def access_token_tenant_b(user_tenant_b: User) -> str:
    return create_access_token(user_tenant_b)


@pytest.fixture
def auth_cookies_tenant_a(access_token_tenant_a: str) -> dict[str, str]:
    return {"access_token": access_token_tenant_a}


@pytest.fixture
def auth_cookies_tenant_b(access_token_tenant_b: str) -> dict[str, str]:
    return {"access_token": access_token_tenant_b}


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
