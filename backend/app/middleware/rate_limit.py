"""Sliding-window rate limiting middleware."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings


class RateLimiterStore:
    """Thread-safe sliding-window request store."""

    def __init__(self) -> None:
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self.total_blocked: int = 0

    def allow(self, key: str, limit: int, window_seconds: int = 60) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            q = self._hits[key]
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= limit:
                self.total_blocked += 1
                retry_after = max(1, int(window_seconds - (now - q[0])))
                return False, retry_after
            q.append(now)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
            self.total_blocked = 0


rate_limiter_store = RateLimiterStore()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Applies per-client sliding-window rate limits to API endpoints."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path in ("/api/health", "/docs", "/openapi.json", "/"):
            return await call_next(request)

        settings = get_settings()
        client_host = request.client.host if request.client else "unknown"
        auth_header = request.headers.get("authorization", "")
        # Differentiate authenticated callers without storing raw tokens
        key = f"{client_host}:{hash(auth_header)}" if auth_header else client_host

        allowed, retry_after = rate_limiter_store.allow(
            key=key,
            limit=settings.rate_limit_per_minute,
            window_seconds=60,
        )
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please wait before retrying."},
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)

