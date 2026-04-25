"""Re-export canonical models for backward compatibility.

Historically this module declared its own `User`, `Organization` and
`RefreshToken` SQLAlchemy mappers, which collided with `app.models.*` and
broke the metadata at import time (`Table 'users' is already defined`).

The canonical mappers now live in `app.models`. This file only re-exports
them so existing imports `from app.users.models import User` keep working.
"""

from __future__ import annotations

from app.models.organization import Organization as Organization
from app.models.refresh_token import RefreshToken as RefreshToken
from app.models.user import User as User

__all__ = ["Organization", "RefreshToken", "User"]
