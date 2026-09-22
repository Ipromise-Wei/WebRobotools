import logging

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.core.auth import (
    AuthenticationLockedError,
    AuthManager,
    SESSION_COOKIE,
)


router = APIRouter()
LOGGER = logging.getLogger(__name__)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class AuthStatus(BaseModel):
    enabled: bool
    authenticated: bool
    username: str = ""
    expires_at: int | None = None


def _manager(request: Request) -> AuthManager:
    return request.app.state.auth_manager


@router.get("/status", response_model=AuthStatus)
async def auth_status(request: Request, response: Response) -> AuthStatus:
    response.headers["Cache-Control"] = "no-store"
    manager = _manager(request)
    identity = manager.validate_session(request.cookies.get(SESSION_COOKIE))
    return AuthStatus(
        enabled=manager.enabled,
        authenticated=identity is not None,
        username=identity.username if identity else "",
        expires_at=identity.expires_at if identity else None,
    )


@router.post("/login", response_model=AuthStatus)
async def login(payload: LoginRequest, request: Request, response: Response) -> AuthStatus:
    response.headers["Cache-Control"] = "no-store"
    manager = _manager(request)
    client_id = request.client.host if request.client else "unknown"
    try:
        valid = manager.authenticate(payload.username, payload.password, client_id)
    except AuthenticationLockedError as exc:
        LOGGER.warning("Login rate limit reached for client %s", client_id)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    if not valid:
        LOGGER.warning("Rejected login attempt from client %s", client_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    token, identity = manager.issue_session(payload.username)
    LOGGER.info("Administrator %r signed in from %s", identity.username, client_id)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=manager.settings.session_hours * 3600,
        httponly=True,
        secure=manager.settings.cookie_secure,
        samesite="strict",
        path="/",
    )
    return AuthStatus(
        enabled=manager.enabled,
        authenticated=True,
        username=identity.username,
        expires_at=identity.expires_at,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response) -> None:
    identity = _manager(request).validate_session(request.cookies.get(SESSION_COOKIE))
    if identity:
        LOGGER.info("Administrator %r signed out", identity.username)
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=_manager(request).settings.cookie_secure,
        samesite="strict",
    )
