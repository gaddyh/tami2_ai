# dedupe/cache.py
from datetime import datetime, timedelta

class IdempotencyCache:
    def __init__(self, ttl_seconds: int = 3600):
        self.ttl = timedelta(seconds=ttl_seconds)
        self.store: dict[str, datetime] = {}

    def _purge(self):
        now = datetime.utcnow()
        expired = [k for k, ts in self.store.items() if now - ts > self.ttl]
        for k in expired:
            del self.store[k]

    def seen(self, key: str) -> bool:
        """
        check ONLY. do not auto insert.
        """
        self._purge()
        return key in self.store

    def mark(self, key: str):
        """
        manually mark as seen now.
        """
        self._purge()
        self.store[key] = datetime.utcnow()


# global instance (for MVP)
idempotency_cache = IdempotencyCache(ttl_seconds=3600)  # 1h
