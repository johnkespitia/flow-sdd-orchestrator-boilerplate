from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class SlidingWindowRateLimiter:
    window_seconds: int
    max_requests: int
    _buckets: dict[str, list[float]] = field(default_factory=dict)

    def allow(self, key: str) -> bool:
        now = time.time()
        start = now - float(max(1, self.window_seconds))
        bucket = self._buckets.setdefault(key, [])
        # Compact old hits.
        fresh = [item for item in bucket if item >= start]
        if len(fresh) >= max(1, self.max_requests):
            self._buckets[key] = fresh
            return False
        fresh.append(now)
        self._buckets[key] = fresh
        return True

