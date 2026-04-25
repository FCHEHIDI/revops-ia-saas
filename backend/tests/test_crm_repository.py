import pytest
from uuid import uuid4
from app.crm.repository import (
    create_account, get_account, update_account, search_accounts
)
from app.crm.schemas import AccountCreate

@pytest.mark.asyncio
async def test_account_crud(test_db):
    acc = await create_account(test_db, AccountCreate(name="ACME"), uuid4(), uuid4())
    fetched = await get_account(test_db, acc.id)
    assert fetched is not None
    fetched2 = await update_account(test_db, acc.id, {"name": "ACME Corp"})
    assert fetched2.name == "ACME Corp"
    accs, _ = await search_accounts(test_db, None, None, 1, 10)
    assert any(a.id == acc.id for a in accs)
