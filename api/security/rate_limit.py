"""Cloud Run demo trafiği için küçük, bağımlılıksız bir hız sınırlayıcı."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Any, Deque, Dict, Tuple

from fastapi import HTTPException

from api.config import settings
from api.security.auth import UserSession


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._events: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    @staticmethod
    def _client_key(request: Any) -> str:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            # Cloud Run/GFE güvenilir istemci ve proxy adreslerini sağ tarafa ekler;
            # kullanıcı tarafından eklenebilen soldaki değerleri anahtar olarak kullanma.
            parts = [part.strip() for part in forwarded.split(",") if part.strip()]
            if len(parts) >= 2:
                return parts[-2]
            if parts:
                return parts[-1]
        return getattr(getattr(request, "client", None), "host", "unknown")

    def check(self, request: Any, user: UserSession, scope: str, limit: int) -> None:
        if settings.ENVIRONMENT != "production" or not user.user_id.startswith("demo_"):
            return
        safe_limit = max(1, limit)
        now = time.monotonic()
        cutoff = now - 60.0
        key = (scope, self._client_key(request))
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= safe_limit:
                retry_after = max(1, int(60 - (now - events[0])))
                raise HTTPException(
                    status_code=429,
                    detail="Demo kullanım sınırına ulaşıldı. Lütfen kısa süre sonra yeniden deneyin.",
                    headers={"Retry-After": str(retry_after)},
                )
            events.append(now)

            if len(self._events) > 5000:
                stale = [k for k, q in self._events.items() if not q or q[-1] <= cutoff]
                for stale_key in stale[:1000]:
                    self._events.pop(stale_key, None)


demo_rate_limiter = SlidingWindowRateLimiter()
