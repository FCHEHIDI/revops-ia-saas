from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.common.db import get_db
from app.config import settings
from app.rate_limiter import limiter
from app.auth.dependencies import get_current_active_user
from app.auth.schemas import (
    DisableMFARequest,
    EnableMFARequest,
    LoginRequest,
    MessageResponse,
    MFASetupResponse,
    RegisterRequest,
    UserResponse,
)
from app.auth.service import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    get_password_hash,
    get_password_hash_async,
    generate_mfa_secret,
    get_totp,
    refresh_tokens,
    revoke_refresh_token,
    verify_mfa_code,
    verify_password,
)
from app.models.organization import Organization
from app.models.user import User

router = APIRouter()


def _require_admin(user: User) -> None:
    if "admin" not in (user.roles or []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )


def _require_admin_debug_enabled() -> None:
    if not settings.admin_debug_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )

_ACCESS_MAX_AGE = 15 * 60  # 15 minutes
_REFRESH_MAX_AGE = 7 * 24 * 3600  # 7 days


def _set_auth_cookies(
    response: Response, access_token: str, refresh_token: str
) -> None:
    is_prod = settings.environment == "production"
    # In dev the frontend (e.g. http://localhost:13000) talks to the API
    # (http://localhost:18000) cross-port, which is cross-origin from the
    # browser's perspective. `SameSite=strict` would refuse to send the
    # cookie on XHR/fetch in that case. We therefore use:
    #   - dev:  SameSite=lax + Secure=False (works on http://localhost)
    #   - prod: SameSite=strict + Secure=True (full hardening)
    samesite: str = "strict" if is_prod else "lax"
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite=samesite,
        secure=is_prod,
        max_age=_ACCESS_MAX_AGE,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        samesite=samesite,
        secure=is_prod,
        max_age=_REFRESH_MAX_AGE,
        path="/",
    )


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
@limiter.limit("5/minute")
async def register(
    data: RegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    # Tenant resolution:
    # - If `data.tenant_id` is provided, the caller expects to join an existing
    #   organization (e.g. invite flow). We refuse if the org does not exist
    #   to keep tenant isolation strict.
    # - Otherwise we provision a fresh organization so the new account has its
    #   own isolated workspace (single sign-up flow).
    if data.tenant_id is not None:
        existing_org = await db.execute(
            select(Organization).where(Organization.id == data.tenant_id)
        )
        if not existing_org.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unknown tenant_id",
            )
        tenant_id = data.tenant_id
    else:
        import re
        tenant_id = uuid4()
        org_name = data.company_name or f"{data.full_name or data.email.split('@')[0]}'s workspace"
        # Generate URL-safe slug: lowercase, collapse non-alphanumeric to hyphens
        _base_slug = re.sub(r"[^a-z0-9]+", "-", org_name.lower()).strip("-")
        org_slug = f"{_base_slug[:48]}-{tenant_id.hex[:8]}"
        db.add(
            Organization(
                id=tenant_id,
                name=org_name,
                slug=org_slug,
                plan="free",
            )
        )
        await db.flush()

    user = User(
        id=uuid4(),
        email=data.email,
        password_hash=await get_password_hash_async(data.password),
        full_name=data.full_name,
        org_id=tenant_id,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(user)
    refresh_token = await create_refresh_token(db, user)
    _set_auth_cookies(response, access_token, refresh_token)

    return UserResponse.model_validate(user)


@router.post("/login", response_model=UserResponse)
@limiter.limit("10/minute")
async def login(
    data: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    user = await authenticate_user(db, data.email, data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if user.mfa_enabled:
        if not data.mfa_code:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="MFA code required",
            )
        if not user.mfa_secret or not verify_mfa_code(user.mfa_secret, data.mfa_code):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid MFA code",
            )

    access_token = create_access_token(user)
    refresh_token = await create_refresh_token(db, user)
    _set_auth_cookies(response, access_token, refresh_token)

    return UserResponse.model_validate(user)


@router.post("/mfa/setup", response_model=MFASetupResponse)
async def mfa_setup(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MFASetupResponse:
    if not user.mfa_secret:
        user.mfa_secret = generate_mfa_secret()
    user.mfa_enabled = False
    db.add(user)
    await db.commit()
    await db.refresh(user)

    otpauth_uri = get_totp(user.mfa_secret).provisioning_uri(
        user.email, issuer_name="RevOps IA"
    )
    return MFASetupResponse(otpauth_uri=otpauth_uri, secret=user.mfa_secret)


@router.post("/mfa/enable", response_model=UserResponse)
async def mfa_enable(
    data: EnableMFARequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    if not user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA setup required before enabling.",
        )
    if not get_totp(user.mfa_secret).verify(data.code, valid_window=1):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid MFA code.",
        )
    user.mfa_enabled = True
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return UserResponse.model_validate(user)


@router.post("/mfa/disable", response_model=UserResponse)
async def mfa_disable(
    data: DisableMFARequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        )
    if not user.mfa_enabled or not user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not enabled.",
        )
    if not get_totp(user.mfa_secret).verify(data.code, valid_window=1):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid MFA code.",
        )
    user.mfa_enabled = False
    user.mfa_secret = None
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return UserResponse.model_validate(user)


@router.post("/refresh", response_model=MessageResponse)
@limiter.limit("20/minute")
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    raw_refresh_token = request.cookies.get("refresh_token")
    if not raw_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token"
        )

    access_token, new_refresh_token = await refresh_tokens(db, raw_refresh_token)
    _set_auth_cookies(response, access_token, new_refresh_token)

    return MessageResponse(message="Tokens refreshed.")


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    raw_refresh_token = request.cookies.get("refresh_token")
    if raw_refresh_token:
        await revoke_refresh_token(db, raw_refresh_token)

    response.delete_cookie(key="access_token")
    response.delete_cookie(key="refresh_token")

    return MessageResponse(message="Logged out.")


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_active_user)) -> UserResponse:
    return UserResponse.model_validate(user)


@router.get("/me/permissions", response_model=list[str])
async def me_permissions(user: User = Depends(get_current_active_user)) -> list[str]:
    _require_admin_debug_enabled()
    _require_admin(user)
    return user.permissions or []


@router.get("/me/roles", response_model=list[str])
async def me_roles(user: User = Depends(get_current_active_user)) -> list[str]:
    _require_admin_debug_enabled()
    _require_admin(user)
    return user.roles or []
