import pytest
from app.crm.repository import create_account, get_account
from uuid import uuid4
import os

def is_postgres_available():
    return os.environ.get("TEST_DB_VENDOR", "postgres").startswith("postgres")

@pytest.mark.skipif(not is_postgres_available(), reason="RLS only relevant for Postgres")
@pytest.mark.asyncio
async def test_tenant_rls(test_db):
    tenant_a = uuid4()
    tenant_b = uuid4()
    user_id = uuid4()
    acc_a = await create_account(test_db, {"name": "TenantA"}, user_id, tenant_a)
    # forcibly set tenant context for B
    await test_db.execute("SELECT set_config('app.current_tenant_id', :tid, true)", {"tid": str(tenant_b)})
    acc = await get_account(test_db, acc_a.id)
    assert acc is None
