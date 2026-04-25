"""Root conftest: load test env vars BEFORE any `app.*` import.

Pytest discovers this file before `tests/conftest.py`, so any module imported
from `tests/conftest.py` (which itself imports `app.*`) will see these
environment variables. This avoids the need to maintain a `.env.test` file.
"""

from __future__ import annotations

import os

_TEST_ENV_DEFAULTS: dict[str, str] = {
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/revops_test",
    "JWT_SECRET": "test-jwt-secret-not-for-production",
    "JWT_ALGORITHM": "HS256",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "60",
    "REFRESH_TOKEN_EXPIRE_DAYS": "7",
    "INTERNAL_SECRET": "test-internal-secret-not-for-production",
    "ORCHESTRATOR_URL": "http://orchestrator-test:8001",
    "INTERNAL_API_KEY": "test-internal-api-key",
}

for _key, _value in _TEST_ENV_DEFAULTS.items():
    os.environ.setdefault(_key, _value)
