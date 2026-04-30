"""
Shared fixtures for mcp-crm tests.

All tests run without a real backend — httpx calls are intercepted by respx.
"""

from __future__ import annotations

import sys
import os

# Ensure src/ is on sys.path so imports resolve correctly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
import httpx
import respx

from config import Settings
from constants import (
    VALID_TENANT_ID,
    VALID_CONTACT_ID,
    VALID_ACCOUNT_ID,
    VALID_DEAL_ID,
    VALID_USER_ID,
    MOCK_BACKEND_URL,
)


@pytest.fixture
def test_settings() -> Settings:
    """Overrides Settings with mock values — no .env file required."""
    return Settings(
        BACKEND_URL=MOCK_BACKEND_URL,
        INTERNAL_API_KEY="test-internal-key",
        PORT=9001,
        LOG_LEVEL="DEBUG",
        HTTP_TIMEOUT=5.0,
    )


@pytest.fixture
def valid_tenant_id() -> str:
    return VALID_TENANT_ID


@pytest.fixture
def valid_contact_id() -> str:
    return VALID_CONTACT_ID


@pytest.fixture
def valid_account_id() -> str:
    return VALID_ACCOUNT_ID


@pytest.fixture
def valid_deal_id() -> str:
    return VALID_DEAL_ID


@pytest.fixture
def valid_user_id() -> str:
    return VALID_USER_ID


@pytest.fixture
def mock_contact() -> dict:
    return {
        "id": VALID_CONTACT_ID,
        "org_id": VALID_TENANT_ID,
        "first_name": "Alice",
        "last_name": "Dupont",
        "email": "alice@example.com",
        "phone": "+33600000001",
        "job_title": "CEO",
        "account_id": VALID_ACCOUNT_ID,
        "status": "active",
        "created_by": VALID_USER_ID,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }


@pytest.fixture
def mock_account() -> dict:
    return {
        "id": VALID_ACCOUNT_ID,
        "org_id": VALID_TENANT_ID,
        "name": "Acme Corp",
        "domain": "acme.com",
        "industry": "Technology",
        "size": "51-200",
        "arr": "120000.00",
        "status": "active",
        "created_by": VALID_USER_ID,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }


@pytest.fixture
def mock_deal() -> dict:
    return {
        "id": VALID_DEAL_ID,
        "org_id": VALID_TENANT_ID,
        "account_id": VALID_ACCOUNT_ID,
        "contact_id": VALID_CONTACT_ID,
        "owner_id": VALID_USER_ID,
        "title": "Enterprise deal",
        "stage": "prospecting",
        "amount": "50000.00",
        "currency": "USD",
        "close_date": "2026-06-30",
        "probability": 0.2,
        "notes": None,
        "created_by": VALID_USER_ID,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }


@pytest.fixture
def mock_client(test_settings: Settings):
    """
    Yields (httpx.AsyncClient, respx.MockRouter).
    The client is pre-configured with mock backend URL and API key.
    respx intercepts all outgoing HTTP calls within the test.
    """
    with respx.mock(base_url=MOCK_BACKEND_URL, assert_all_called=False) as router:
        client = httpx.AsyncClient(
            base_url=MOCK_BACKEND_URL,
            timeout=httpx.Timeout(5.0),
            headers={
                "X-Internal-API-Key": test_settings.INTERNAL_API_KEY,
                "Content-Type": "application/json",
            },
        )
        yield client, router
