"""
Simple in-memory sliding-window rate limiter.

`settings.RATE_LIMIT_LOGIN_PER_MINUTE` / `RATE_LIMIT_AI_PER_MINUTE` were
already defined but never enforced anywhere — login and the AI-backed
endpoints (assistant query, document extraction) were fully open to brute
force / cost-abuse. This closes that gap.

This is process-local (a dict guarded by a lock), which is the right amount
of complexity for a single-process deployment (this project's Docker Compose
setup runs one API container) and needs no extra infrastructure. It is
NOT shared across multiple worker processes/instances — if this is ever
scaled horizontally behind a load balancer, swap this for a Redis-backed
implementation (REDIS_URL is already configured) using the same interface.
"""
import threading
import time

from fastapi import HTTPException, Request, status

from app.core.config import settings

_lock = threading.Lock()
# key -> list of monotonic timestamps of recent requests within the window
_hits: dict[str, list[float]] = {}
WINDOW_SECONDS = 60.0


def _client_key(request: Request, scope: str) -> str:
    # X-Forwarded-For is only trustworthy behind a controlled reverse proxy
    # (this app's nginx.conf/Docker Compose setup); fall back to the direct
    # peer address otherwise.
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    return f"{scope}:{ip}"


def enforce_rate_limit(request: Request, scope: str, limit_per_minute: int) -> None:
    if limit_per_minute <= 0:
        return  # 0/negative disables the limit, e.g. for tests
    key = _client_key(request, scope)
    now = time.monotonic()
    cutoff = now - WINDOW_SECONDS
    with _lock:
        hits = [t for t in _hits.get(key, []) if t > cutoff]
        if len(hits) >= limit_per_minute:
            _hits[key] = hits
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please wait a moment and try again.",
                headers={"Retry-After": str(int(WINDOW_SECONDS))},
            )
        hits.append(now)
        _hits[key] = hits


def rate_limit_login(request: Request) -> None:
    enforce_rate_limit(request, "login", settings.RATE_LIMIT_LOGIN_PER_MINUTE)


def rate_limit_ai(request: Request) -> None:
    enforce_rate_limit(request, "ai", settings.RATE_LIMIT_AI_PER_MINUTE)
