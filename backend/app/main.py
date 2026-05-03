import asyncio
import contextlib
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.rate_limiter import limiter

from app.middleware.tenant import TenantMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.auth import router as auth_router
from app.users import router as users_router
from app.sessions import router as sessions_router
from app.orchestrator import router as orchestrator_router
from app.crm import router as crm_router
from app.crm.public_router import router as crm_public_router
from app.documents import router as documents_router
from app.audit import router as audit_router
from app.proxy import router as proxy_router
from app.onboarding import router as onboarding_router
from app.notifications import router as notifications_router
from app.api_keys.router import router as api_keys_router
from app.webhooks.router import router as webhooks_router
from app.webhooks.service import run_worker as _run_webhook_worker
from app.activities.router import router as activities_router
from app.email_delivery.router import router as email_router, tracking_router as email_tracking_router
from app.scoring.router import router as scoring_router
from app.playbooks.router import router as playbooks_router, internal_router as playbooks_internal_router
from app.playbooks.worker import run_worker as _run_playbook_worker
from app.email_delivery.service import run_worker as _run_email_worker
from app.reports.router import router as reports_router
from app.usage.router import router as usage_router
from app.common.db import AsyncSessionLocal
from sqlalchemy import text as sa_text


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Manage application lifecycle: start webhook worker on startup, cancel on shutdown."""

    @contextlib.asynccontextmanager
    async def _db_factory():
        async with AsyncSessionLocal() as session:
            yield session

    worker_task = asyncio.create_task(_run_webhook_worker(_db_factory))
    email_worker_task = asyncio.create_task(_run_email_worker(_db_factory))
    playbook_worker_task = asyncio.create_task(_run_playbook_worker(_db_factory))
    try:
        yield
    finally:
        for task in (worker_task, email_worker_task, playbook_worker_task):
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

app = FastAPI(title="RevOps IA SaaS API", version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------------------------# ---------------------------------------------------------------------------
# CORS — required for the Next.js frontend to call the API from the browser.
# In dev the frontend may run on any localhost port (3000, 3001, 13000...),
# so we accept the entire localhost regex when ENVIRONMENT=development.
# In production, set CORS_ALLOWED_ORIGINS to the explicit list of trusted
# origins (comma-separated) and remove the regex.
# ---------------------------------------------------------------------------
_env = os.getenv("ENVIRONMENT", "development").lower()
_explicit_origins = [
    o.strip()
    for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
    if o.strip()
]

cors_kwargs: dict = {
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
if _env == "development":
    cors_kwargs["allow_origin_regex"] = (
        r"^http://(localhost|127\.0\.0\.1)(:\d+)?$"
    )
    cors_kwargs["allow_origins"] = _explicit_origins or []
else:
    cors_kwargs["allow_origins"] = _explicit_origins

# Starlette stacks middlewares in LIFO order: the LAST `add_middleware`
# call wraps the previous ones, so CORSMiddleware MUST be added AFTER
# TenantMiddleware to intercept preflight OPTIONS first and short-circuit
# the tenant/JWT enforcement.
app.add_middleware(TenantMiddleware)
app.add_middleware(CORSMiddleware, **cors_kwargs)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(auth_router.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(users_router.router, prefix="/api/v1/users", tags=["users"])
app.include_router(sessions_router.router, prefix="/api/v1/sessions", tags=["sessions"])
app.include_router(
    orchestrator_router.router, prefix="/internal", tags=["orchestrator"]
)
app.include_router(
    crm_router.router, prefix="/internal/v1/crm", tags=["crm-internal"]
)
app.include_router(
    crm_public_router, prefix="/api/v1/crm", tags=["crm"]
)
app.include_router(
    documents_router.router, prefix="/api/v1/documents", tags=["documents"]
)
app.include_router(audit_router.router, prefix="/api/v1/audit", tags=["audit"])
app.include_router(proxy_router.router, prefix="/api/v1", tags=["proxy"])
app.include_router(
    onboarding_router.router, prefix="/api/v1", tags=["onboarding"]
)
app.include_router(notifications_router, tags=["notifications"])
app.include_router(
    api_keys_router, prefix="/api/v1/api-keys", tags=["api-keys"]
)
app.include_router(
    webhooks_router, prefix="/api/v1/webhooks", tags=["webhooks"]
)
app.include_router(
    activities_router, prefix="/api/v1/activities", tags=["activities"]
)
app.include_router(
    email_router, prefix="/internal/v1/email", tags=["email"]
)
app.include_router(
    email_tracking_router, prefix="", tags=["email-tracking"]
)
app.include_router(
    scoring_router, prefix="/internal/v1/scoring", tags=["scoring"]
)
app.include_router(
    playbooks_router, prefix="/api/v1/playbooks", tags=["playbooks"]
)
app.include_router(
    playbooks_internal_router, prefix="/internal/v1/playbooks", tags=["playbooks-internal"]
)
app.include_router(
    reports_router, prefix="/api/v1/reports", tags=["reports"]
)
app.include_router(
    usage_router, prefix="/api/v1/billing", tags=["billing"]
)


@app.get("/health")
async def health() -> dict:
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(sa_text("SELECT 1"))
        return {"status": "ok", "db": "ok"}
    except Exception:
        return {"status": "degraded", "db": "error"}
