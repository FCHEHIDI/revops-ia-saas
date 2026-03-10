from typing import AsyncGenerator, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base
from starlette.requests import Request

from app.config import settings

Base = declarative_base()
engine = create_async_engine(settings.database_url, future=True, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Fournit une session DB avec RLS activé si tenant_id est disponible dans request.state.

    Conforme ADR-005 : positionne app.current_tenant_id avant toute requête ORM
    de façon à ce que les politiques RLS PostgreSQL soient actives.
    """
    async with AsyncSessionLocal() as session:
        tenant_id: Optional[UUID] = getattr(request.state, "tenant_id", None)
        if tenant_id is not None:
            await session.execute(
                text("SELECT set_config('app.current_tenant_id', :tid, true)"),
                {"tid": str(tenant_id)},
            )
        yield session


async def set_tenant(db: AsyncSession, tenant_id: str) -> None:
    """Positionne manuellement app.current_tenant_id sur une session existante."""
    await db.execute(
        text("SELECT set_config('app.current_tenant_id', :tid, true)"),
        {"tid": tenant_id},
    )
