"""Minimal cookie-session auth for the dashboard.

In-memory session store (single process; tokens reset on restart -> re-login).
Twilio webhooks stay public; only the dashboard and /api/* are gated.
"""
from __future__ import annotations

import secrets
import time

from fastapi import HTTPException, Request

from . import config

COOKIE = "mu_session"
TTL = 60 * 60 * 8  # 8 hours

_SESSIONS: dict[str, float] = {}   # token -> expiry epoch


def check_credentials(username: str, password: str) -> bool:
    return (secrets.compare_digest(username or "", config.ADMIN_USERNAME)
            and secrets.compare_digest(password or "", config.ADMIN_PASSWORD))


def create_session() -> str:
    token = secrets.token_urlsafe(32)
    _SESSIONS[token] = time.time() + TTL
    return token


def destroy_session(token: str | None) -> None:
    if token:
        _SESSIONS.pop(token, None)


def is_valid(token: str | None) -> bool:
    if not token:
        return False
    exp = _SESSIONS.get(token)
    if not exp:
        return False
    if exp < time.time():
        _SESSIONS.pop(token, None)
        return False
    return True


def require_auth(request: Request) -> bool:
    """FastAPI dependency: 401 unless a valid session cookie is present."""
    if not is_valid(request.cookies.get(COOKIE)):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return True
