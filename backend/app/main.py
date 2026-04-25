from fastapi import FastAPI
from app.middleware.tenant import TenantMiddleware
from app.auth import router as auth_router
from app.users import router as users_router
from app.sessions import router as sessions_router
from app.orchestrator import router as orchestrator_router
from app.crm import router as crm_router
from app.documents import router as documents_router
from app.audit import router as audit_router

app = FastAPI(title="RevOps IA SaaS API", version="1.0.0")

app.add_middleware(TenantMiddleware)

app.include_router(auth_router.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(users_router.router, prefix="/api/v1/users", tags=["users"])
app.include_router(sessions_router.router, prefix="/api/v1/sessions", tags=["sessions"])
app.include_router(
    orchestrator_router.router, prefix="/internal", tags=["orchestrator"]
)
app.include_router(
    crm_router.router, prefix="/internal/v1/crm", tags=["crm"]
)
app.include_router(
    documents_router.router, prefix="/api/v1/documents", tags=["documents"]
)
app.include_router(audit_router.router, prefix="/api/v1/audit", tags=["audit"])


@app.get("/health")
def health():
    return {"status": "ok"}
