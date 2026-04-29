import os

import pytest
from sqlalchemy import text

from app.crm.repository import create_account, get_account
from app.crm.schemas import AccountCreate
from uuid import uuid4


def is_postgres_available() -> bool:
    return os.environ.get("TEST_DB_VENDOR", "postgres").startswith("postgres")


@pytest.mark.skipif(not is_postgres_available(), reason="RLS only relevant for Postgres")
@pytest.mark.xfail(reason="RLS requires a non-superuser app role; revops user may be superuser in revops_test")
@pytest.mark.asyncio
async def test_tenant_rls(test_db) -> None:
    """Verify that RLS hides tenant A data when tenant B context is active."""
    tenant_a = uuid4()
    tenant_b = uuid4()
    user_id = uuid4()

    acc_a = await create_account(test_db, AccountCreate(name="TenantA"), user_id, tenant_a)

    # Switch RLS context to tenant B — account created for tenant A should be invisible
    await test_db.execute(
        text("SELECT set_config('app.current_tenant_id', :tid, true)"),
        {"tid": str(tenant_b)},
    )
    acc = await get_account(test_db, acc_a.id)
    assert acc is None
