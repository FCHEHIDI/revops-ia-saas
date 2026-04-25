from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.common.db import get_db
from app.config import settings
from app.auth.dependencies import get_current_active_user
from app.auth.schemas import (
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    UserResponse,
)
from app.auth.service import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    get_password_hash,
    refresh_tokens,
    revoke_refresh_token,
)
from app.models.organization import Organization
from app.models.user import User

router = APIRouter()

_ACCESS_MAX_AGE = 15 * 60  # 15 minutes
_REFRESH_MAX_AGE = 7 * 24 * 3600  # 7 days


def _set_auth_cookies(
    response: Response, access_token: str, refresh_token: str
) -> None:
    secure = settings.environment == "production"
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="strict",
        secure=secure,
        max_age=_ACCESS_MAX_AGE,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        samesite="strict",
        secure=secure,
        max_age=_REFRESH_MAX_AGE,
    )


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
async def register(
    data: RegisterRequest,
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
        tenant_id = uuid4()
        org_slug = f"org-{tenant_id.hex[:8]}"
        org_name = data.full_name or data.email.split("@")[0]
        db.add(
            Organization(
                id=tenant_id,
                name=f"{org_name}'s workspace",
                slug=org_slug,
                plan="free",
            )
        )
        await db.flush()

    user = User(
        id=uuid4(),
        email=data.email,
        password_hash=get_password_hash(data.password),
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
async def login(
    data: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    user = await authenticate_user(db, data.email, data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    access_token = create_access_token(user)
    refresh_token = await create_refresh_token(db, user)
    _set_auth_cookies(response, access_token, refresh_token)

    return UserResponse.model_validate(user)


@router.post("/refresh", response_model=MessageResponse)
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
