# message_index.py
import time, threading

class MessageIndex:
    """wamid -> raw message object (exact message dict the API gives you)."""
    def __init__(self, ttl_seconds: int = 48 * 3600):
        self._ttl = ttl_seconds
        self._lock = threading.RLock()
        self._map: dict[str, tuple[float, dict]] = {}

    def put(self, wamid: str, msg: dict) -> None:
        if not wamid or not msg:
            return
        with self._lock:
            self._map[wamid] = (time.time(), msg)

    def get(self, wamid: str) -> dict | None:
        if not wamid:
            return None
        with self._lock:
            item = self._map.get(wamid)
            if not item:
                return None
            ts, msg = item
            if time.time() - ts > self._ttl:
                self._map.pop(wamid, None)
                return None
            return msg

    def gc(self) -> None:
        now = time.time()
        with self._lock:
            stale = [k for k,(ts,_) in self._map.items() if now - ts > self._ttl]
            for k in stale:
                self._map.pop(k, None)

MESSAGE_INDEX = MessageIndex()
