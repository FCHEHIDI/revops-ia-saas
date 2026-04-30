from fastapi import Request, HTTPException, status, Depends


def get_current_user(request: Request):
    user_id = getattr(request.state, "user_id", None)
    tenant_id = getattr(request.state, "tenant_id", None)
    permissions = getattr(request.state, "permissions", [])
    if not user_id or not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    return {"user_id": user_id, "tenant_id": tenant_id, "permissions": permissions}


def require_permission(permission: str):
    def dependency(request: Request = Depends()):
        permissions = getattr(request.state, "permissions", [])
        if permission not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied"
            )

    return dependency
