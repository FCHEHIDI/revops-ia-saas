from fastapi import APIRouter, Depends, Response, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.common.db import get_db
from app.auth.schemas import LoginRequest, TokenResponse, RefreshRequest
from app.auth.service import authenticate_user, create_tokens, refresh_access_token, revoke_refresh_token

router = APIRouter()

@router.post("/login", response_model=TokenResponse)
async def login(request_data: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, request_data.email, request_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    tokens = await create_tokens(db, user)
    response.set_cookie(
        key="refresh_token", value=tokens.refresh_token,
        httponly=True, max_age=tokens.expires_in
    )
    return tokens

@router.post("/refresh", response_model=TokenResponse)
async def refresh(r: RefreshRequest = None, db: AsyncSession = Depends(get_db), response: Response = None):
    refresh_token = r.refresh_token if r else None
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")
    token_data = await refresh_access_token(db, refresh_token)
    response.set_cookie(key="refresh_token", value=token_data.refresh_token, httponly=True, max_age=token_data.expires_in)
    return token_data

@router.post("/logout")
async def logout(r: RefreshRequest = None, db: AsyncSession = Depends(get_db)):
    refresh_token = r.refresh_token if r else None
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")
    await revoke_refresh_token(db, refresh_token)
    return {"detail": "Logged out"}
