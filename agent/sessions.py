# sessions.py
import os, threading
from pathlib import Path
from typing import Optional, Iterable, List, Dict, Any
from agents import SQLiteSession  # keep or swap later to SQLAlchemySession

_SESSION_ROOT = Path(os.getenv("TAMI_SESSION_DIR", ".sessions"))
_SESSION_CACHE: dict[str, "ManagedSession"] = {}
_SESSION_LOCK = threading.Lock()

# ~40 turns ≈ 80 messages (user+assistant+tools)
MAX_MESSAGES_FOR_MODEL = 60


class ManagedSession:
    """
    Async wrapper that conforms to the Agents SDK's Session API,
    but keeps things simple:
    - get_items(): returns last N messages only (bounded context).
    - add_items(): write-through to SQLiteSession.
    """

    def __init__(self, base_session):
        self._base = base_session

    async def get_items(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        # Ignore caller limit; enforce our own
        try:
            return list(await self._base.get_items(MAX_MESSAGES_FOR_MODEL))
        except TypeError:
            # In case SQLiteSession.get_items has a different signature
            return list(await self._base.get_items())

    async def add_items(self, items: Iterable[Dict[str, Any]]) -> None:
        # Just append to the underlying session; no summarization
        await self._base.add_items(list(items))

    async def clear_session(self) -> None:
        await self._base.clear_session()

    async def pop_item(self) -> Optional[Dict[str, Any]]:
        return await self._base.pop_item()

    # Optional escape hatch (for debugging)
    async def raw_get_items(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        try:
            return list(await self._base.get_items(limit))
        except TypeError:
            return list(await self._base.get_items(10_000))


def _key(user_id: str, thread_id: str) -> str:
    return f"{user_id}:{thread_id}"


def _create_base_session(user_id: str, thread_id: str):
    path = _SESSION_ROOT / user_id / f"{thread_id}.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    return SQLiteSession(str(path))


def get_session(user_id: str, thread_id: str) -> ManagedSession:
    """
    Return a ManagedSession (async Session). Your runner keeps calling only get_session(...),
    and the Agents SDK will await its methods.
    """
    k = _key(user_id, thread_id)
    with _SESSION_LOCK:
        if k in _SESSION_CACHE:
            return _SESSION_CACHE[k]

        base = _create_base_session(user_id, thread_id)
        managed = ManagedSession(base)
        _SESSION_CACHE[k] = managed
        return managed
