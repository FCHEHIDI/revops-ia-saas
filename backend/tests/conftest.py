import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.common.db import AsyncSessionLocal
import asyncio

@pytest.fixture
def test_client():
    return TestClient(app)

@pytest.fixture(scope="function")
async def db_session():
    async with AsyncSessionLocal() as session:
        yield session

@pytest.fixture
def tenant_a_headers():
    return {"Authorization": "Bearer tenant_a_jwt"}

@pytest.fixture
def tenant_b_headers():
    return {"Authorization": "Bearer tenant_b_jwt"}
