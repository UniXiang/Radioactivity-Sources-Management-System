from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status


async def services(request: Request):
    return request.app.state.services


async def current_user(request: Request, service=Depends(services)) -> dict:
    user = service.auth.get_session_user(request.cookies.get("jcsms_session"))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "AUTH_REQUIRED", "message": "Login required"})
    return user


async def public_viewer(request: Request, service=Depends(services)) -> dict:
    """Return a session user or the anonymous read-only viewer identity."""
    user = service.auth.get_session_user(request.cookies.get("jcsms_session"))
    if user is not None:
        return user
    return {"id": None, "username": "viewer", "role": "viewer", "guest": True}


def require_role(*roles: str):
    async def dependency(user=Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": "FORBIDDEN", "message": "Insufficient permissions"})
        return user

    return dependency


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None
