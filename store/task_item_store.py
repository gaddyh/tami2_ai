# store/task_item_store.py
from __future__ import annotations

import logging
from typing import List, Optional, Union, Dict, Any, Literal
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from db.base import db
from shared import time
from models.task_item import TaskItem
logger = logging.getLogger(__name__)
DEFAULT_TZ = ZoneInfo("Asia/Jerusalem")


# --- Time helpers -------------------------------------------------------------

def _ensure_aware_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def _parse_to_utc(dt_in: Optional[Union[str, datetime]]) -> Optional[datetime]:
    if not dt_in:
        return None
    parsed = dt_in if isinstance(dt_in, datetime) else time.parse_datetime(dt_in)
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        parsed = parsed.replace(tzinfo=DEFAULT_TZ)
    return parsed.astimezone(timezone.utc)

class TaskStore:
    """
    Firestore-backed store for tasks. Flexible schema:
    - Create: pass a dict or TaskItem with arbitrary fields. Must include user_id, title.
    - Update: pass a dict of partial changes. Only user_id + item_id required to authorize.
    - Special helper: update_status() (keeps 'completed' in sync if desired).
    """

    def __init__(self):
        self.collection = db.collection("my_tasks")

    # ---------------------- internal utils -----------------------------------

    @staticmethod
    def _to_dict(payload: Union[TaskItem, Dict[str, Any]]) -> Dict[str, Any]:
        if isinstance(payload, TaskItem):
            data = payload.model_dump(exclude_unset=True)
        elif isinstance(payload, dict):
            data = dict(payload)
        else:
            raise TypeError("payload must be dict or TaskItem")
        # 🚫 drop None values
        return {k: v for k, v in data.items() if v is not None}

    def _find_by_op_id(self, user_id: str, op_id: Optional[str]) -> Optional[str]:
        if not op_id:
            return None
        q = (
            self.collection.where("user_id", "==", user_id)
            .where("op_id", "==", op_id)
            .limit(1)
        )
        docs = list(q.stream())
        return docs[0].id if docs else None

    # ------------------------- mutations -------------------------------------

    def create(self, payload: Union[TaskItem, Dict[str, Any]]) -> str:
        """
        Create a task (idempotent by (user_id, op_id) when provided).
        Required fields in payload: user_id (str), title (str).
        Any other fields are accepted as-is.
        Special handling:
          - if 'due' exists (str|datetime), it is normalized to UTC datetime for Firestore.
          - item_type defaults to 'task' if not provided.
        """
        data = self._to_dict(payload)
        user_id = data.get("user_id")
        title = data.get("title")
        if not user_id or not title:
            raise ValueError("create requires user_id and title")

        # idempotency
        existing = self._find_by_op_id(user_id, data.get("op_id"))
        if existing:
            return existing

        # normalize
        now_iso = datetime.now(timezone.utc).isoformat()
        if "due" in data:
            data["due"] = _parse_to_utc(data["due"])
        if "due" not in data:
            data["due"] = None                      # always present (nullable)
        data["status"] = data.get("status") or "pending"
        data.setdefault("item_type", "task")
        data["created_at"] = now_iso
        data["updated_at"] = now_iso

        # assign id and persist
        doc_ref = self.collection.document()
        data["item_id"] = doc_ref.id
        doc_ref.set(data)
        logger.info("[TASKS] Created %s for user %s", doc_ref.id, user_id)
        return doc_ref.id

    def update(self, user_id: str, item_id: str, changes: Dict[str, Any]) -> bool:
        """
        Partial update. `changes` may contain any fields.
        Special handling:
          - if 'due' present: normalized to UTC datetime
          - always refreshes updated_at
        """
        try:
            doc_ref = self.collection.document(item_id)
            snap = doc_ref.get()
            if not snap.exists:
                logger.info("[TASKS] update: not found %s", item_id)
                return False
            cur = snap.to_dict() or {}
            if cur.get("user_id") != user_id:
                logger.warning("[TASKS] update: user mismatch for %s", item_id)
                return False

            changes = {k: v for k, v in (changes or {}).items() if v is not None}

            if "due" in changes:
                changes["due"] = _parse_to_utc(changes["due"])
            changes["updated_at"] = datetime.now(timezone.utc).isoformat()

            # merge update (no field list)
            doc_ref.set(changes, merge=True)
            return True
        except Exception:
            logger.exception("[TASKS] update failed for %s", item_id)
            return False

    def delete(self, user_id: str, item_id: str) -> bool:
        try:
            doc_ref = self.collection.document(item_id)
            snap = doc_ref.get()
            if not snap.exists:
                return False
            if (snap.to_dict() or {}).get("user_id") != user_id:
                return False
            doc_ref.delete()
            return True
        except Exception:
            logger.exception("[TASKS] delete failed for %s", item_id)
            return False

    def update_status(self, user_id: str, item_id: str, status: str, mirror_completed: bool = True) -> bool:
        """
        Minimal, explicit field update for 'status'. If mirror_completed=True:
          completed=True when status=='completed', False when status=='pending' (unchanged otherwise).
        """
        try:
            doc_ref = self.collection.document(item_id)
            snap = doc_ref.get()
            if not snap.exists:
                return False
            data = snap.to_dict() or {}
            if data.get("user_id") != user_id:
                return False

            updates: Dict[str, Any] = {
                "status": status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if mirror_completed:
                if status == "completed":
                    updates["completed"] = True
                elif status == "pending":
                    updates["completed"] = False

            doc_ref.set(updates, merge=True)
            return True
        except Exception:
            logger.exception("[TASKS] update_status failed for %s", item_id)
            return False

    # --------------------------- queries -------------------------------------

    def query_tasks(
        self,
        user_id: str,
        start: datetime,
        end: Optional[datetime] = None,
        statuses: Optional[List[str]] = None,
    ) -> List[dict]:
        """
        For schedulers: tasks due in [start,end], default statuses = ['pending','failed'].
        """
        try:
            statuses = statuses or ["pending", "failed"]
            start_utc = _ensure_aware_utc(start)
            end_utc = _ensure_aware_utc(end) if end else start_utc + timedelta(minutes=1)

            q = (
                self.collection.where("user_id", "==", user_id)
                .where("status", "in", statuses)
                .where("due", ">=", start_utc)
                .where("due", "<=", end_utc)
            )
            return [d.to_dict() for d in q.stream()]
        except Exception:
            logger.exception("[TASKS] query_tasks failed")
            return []

    async def get_upcoming(self, user_id: str) -> List[ActionItemSummary]:
        """
        Next 7 days (status == 'pending').
        """
        try:
            now_fn = getattr(time, "utcnow", None)
            now = now_fn() if callable(now_fn) else datetime.utcnow()
            now = _ensure_aware_utc(now)
            future = now + timedelta(days=7)

            q = (
                self.collection.where("user_id", "==", user_id)
                .where("status", "==", "pending")
                .where("due", ">=", now)
                .where("due", "<=", future)
            )
            out: List[ActionItemSummary] = []
            for doc in q.stream():
                data = doc.to_dict()
                out.append(
                    ActionItemSummary(
                        id=doc.id,
                        action=data.get("title"),
                        action_type="task",
                        time=data.get("due"),
                        participants=[],
                        location=None,
                    )
                )
            return out
        except Exception:
            logger.exception("[TASKS] get_upcoming failed for user %s", user_id)
            return []

    def get_items(
        self,
        user_id: str,
        status: Literal["all", "pending", "completed", "failed"] = "pending",
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        **filters: Any,  # <--- extra ad-hoc filters (e.g., list_id="X", parent_id="Y")
    ) -> List[dict]:
        """
        Flexible list with ad-hoc filters; no fixed field list.
        Known helpers:
          - date bounds on 'due'
          - status='all' skips status filter
        Any extra keyword is applied as equality filter (field == value).
        """
        try:
            q = self.collection.where("user_id", "==", user_id)

            if status != "all":
                q = q.where("status", "==", status)

            if from_date is not None:
                q = q.where("due", ">=", _ensure_aware_utc(from_date))
            if to_date is not None:
                q = q.where("due", "<=", _ensure_aware_utc(to_date))

            for k, v in (filters or {}).items():
                # skip None values; only equality filters here
                if v is not None:
                    q = q.where(k, "==", v)

            try:
                if from_date or to_date:
                    q = q.order_by("due")
            except Exception:
                pass

            return [{"item_id": d.id, **d.to_dict()} for d in q.stream()]
        except Exception:
            logger.exception("[TASKS] get_items failed for user %s", user_id)
            return []

    def query_tasks_due(
        self,
        start: datetime,
        end: datetime,
        statuses: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return tasks (any user) with due in [start, end] and status in (statuses).
        Default statuses: ['pending', 'failed'].
        Results are de-duplicated by item_id and ordered by due ascending (best-effort).

        NOTE: Uses multiple equality scans (one per status) to avoid `where("status", "in", ...)`
        which often requires composite indexes with range filters on `due`.
        """
        try:
            statuses = statuses or ["pending", "failed"]
            start_utc = _ensure_aware_utc(start)
            end_utc = _ensure_aware_utc(end)

            seen: Dict[str, Dict[str, Any]] = {}
            for st in statuses:
                q = (
                    self.collection
                    .where("status", "==", st)
                    .where("due", ">=", start_utc)
                    .where("due", "<=", end_utc)
                    .order_by("due")
                )

                if limit:
                    # Soft limit per status; final dedup may reduce below total*len(statuses)
                    docs = q.limit(limit).stream()
                else:
                    docs = q.stream()

                for d in docs:
                    data = d.to_dict()
                    # Skip tasks without a proper due (just in case)
                    if not data.get("due"):
                        continue
                    # Ensure item_id field exists in returned dict
                    if "item_id" not in data:
                        data["item_id"] = d.id
                    # De-dup by item_id
                    seen[data["item_id"]] = data

            # Best-effort global sort by due
            out = list(seen.values())
            try:
                out.sort(key=lambda x: x.get("due"))
            except Exception:
                pass

            return out
        except Exception:
            logger.exception("[TASKS] query_tasks_due failed")
            return []
