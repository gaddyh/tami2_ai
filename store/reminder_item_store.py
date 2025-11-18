from __future__ import annotations

import logging
from typing import List, Optional, Union
from datetime import datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from db.base import db
from shared import time

from google.cloud.firestore_v1 import FieldFilter  # Firestore filter objects

logger = logging.getLogger(__name__)
DEFAULT_TZ = ZoneInfo("Asia/Jerusalem")


def _ensure_aware_utc(dt: datetime) -> datetime:
    """Normalize any datetime to aware UTC (naive => assume UTC)."""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_to_utc(dt_in: Optional[Union[str, datetime]]) -> Optional[datetime]:
    """
    Parse ISO-8601 string or datetime. If naive, localize to DEFAULT_TZ, then convert to UTC.
    Returns None if input is falsy.
    """
    if not dt_in:
        return None
    parsed = dt_in if isinstance(dt_in, datetime) else time.parse_datetime(dt_in)
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        parsed = parsed.replace(tzinfo=DEFAULT_TZ)
    return parsed.astimezone(timezone.utc)


class ReminderStore:
    """
    Firestore-backed store for ReminderItem (item_type='reminder'), separate collection.
    """

    def __init__(self):
        self.db = db
        self.collection = db.collection("my_reminders")

    # --- Mutations ------------------------------------------------------------

    def update_status(self, user_id: str, item_id: str, status: str) -> bool:
        try:
            doc_ref = self.collection.document(item_id)
            snap = doc_ref.get()
            if not snap.exists:
                logger.info("[REMINDERS] update_status: item %s not found", item_id)
                return False
            data = snap.to_dict() or {}
            if data.get("user_id") != user_id:
                logger.warning("[REMINDERS] update_status: user mismatch for %s", item_id)
                return False
            doc_ref.update(
                {
                    "status": status,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            return True
        except Exception:
            logger.exception("[REMINDERS] update_status failed for %s", item_id)
            return False

    def create_reminder(
        self,
        user_id: str,
        title: str,
        description: Optional[str],
        dt: Optional[Union[str, datetime]],
        op_id: Optional[str] = None,
    ) -> str:
        """
        Create a reminder (item_type='reminder'). Idempotent on (user_id, op_id) if provided.
        """
        try:
            if op_id:
                q = (
                    self.collection
                    .where(filter=FieldFilter("user_id", "==", user_id))
                    .where(filter=FieldFilter("op_id", "==", op_id))
                    .limit(1)
                )
                existing = list(q.stream())
                if existing:
                    return existing[0].id

            dt_utc = _parse_to_utc(dt)
            doc_ref = self.collection.document()
            now_iso = datetime.now(timezone.utc).isoformat()
            doc = {
                "user_id": user_id,
                "item_id": doc_ref.id,
                "item_type": "reminder",
                "title": title,
                "description": description,
                "datetime": dt_utc,  # Firestore Timestamp
                "location": None,    # kept for symmetry; always None here
                "status": "pending",
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            if op_id:
                doc["op_id"] = op_id

            doc_ref.set(doc)
            logger.info("[REMINDERS] Created reminder %s for user %s", doc_ref.id, user_id)
            return doc_ref.id
        except Exception:
            logger.exception("[REMINDERS] create_reminder failed for user %s", user_id)
            raise

    def update_reminder(
        self,
        user_id: str,
        item_id: str,
        title: Optional[str],
        description: Optional[str],
        dt: Optional[Union[str, datetime]],
        status: Optional[str],
    ) -> bool:
        """
        Update an existing reminder. Returns success. Enforces ownership. Converts datetime to UTC.
        """
        try:
            doc_ref = self.collection.document(item_id)
            snap = doc_ref.get()
            if not snap.exists:
                logger.info("[REMINDERS] update_reminder: item %s not found", item_id)
                return False

            current = snap.to_dict() or {}
            if current.get("user_id") != user_id:
                logger.warning("[REMINDERS] update_reminder: user mismatch for %s", item_id)
                return False

            updates: dict = {}
            if title:
                updates["title"] = title
            if description:
                updates["description"] = description
            if dt:
                updates["datetime"] = _parse_to_utc(dt)
            if status:
                updates["status"] = status

            updates["updated_at"] = datetime.now(timezone.utc).isoformat()

            if len(updates) == 1:  # only updated_at
                logger.info("[REMINDERS] update_reminder: no-op for %s", item_id)
                return True

            doc_ref.update(updates)
            logger.info("[REMINDERS] Updated reminder %s for user %s", item_id, user_id)
            return True
        except Exception:
            logger.exception("[REMINDERS] update_reminder failed for %s", item_id)
            return False

    def delete_reminder(self, user_id: str, item_id: str) -> bool:
        try:
            doc_ref = self.collection.document(item_id)
            snap = doc_ref.get()
            if not snap.exists:
                logger.info("[REMINDERS] delete_reminder: item %s not found", item_id)
                return False
            data = snap.to_dict() or {}
            if data.get("user_id") != user_id:
                logger.warning("[REMINDERS] delete_reminder: user mismatch for %s", item_id)
                return False

            doc_ref.delete()
            logger.info("[REMINDERS] Deleted reminder %s for user %s", item_id, user_id)
            return True
        except Exception:
            logger.exception("[REMINDERS] delete_reminder failed for %s", item_id)
            return False

    # --- Queries --------------------------------------------------------------

    def query_reminders(
        self,
        start: datetime,
        end: Optional[datetime] = None,
        *,
        user_id: Optional[str] = None,
        statuses: List[str] = None,
        limit: Optional[int] = None,
    ) -> List[dict]:
        """
        Scheduler query:
        - status in statuses (default: ['pending','failed'])
        - datetime in [start, end]
        - optional user_id filter
        - ordered by datetime ascending
        - optional limit

        NOTE: Firestore may require a composite index for
              (status IN, datetime range, order_by datetime [, user_id]).
        """
        try:
            statuses = statuses or ["pending", "failed"]
            start_utc = _ensure_aware_utc(start)
            end_utc = _ensure_aware_utc(end) if end else start_utc + timedelta(minutes=1)

            q = (
                self.collection
                .where(filter=FieldFilter("status", "in", statuses))
                .where(filter=FieldFilter("datetime", ">=", start_utc))
                .where(filter=FieldFilter("datetime", "<=", end_utc))
            )
            if user_id:
                q = q.where(filter=FieldFilter("user_id", "==", user_id))

            # Firestore requires order_by on the same field used for range filters
            q = q.order_by("datetime")

            if limit and limit > 0:
                q = q.limit(limit)

            return [doc.to_dict() for doc in q.stream()]
        except Exception:
            logger.exception("[REMINDERS] query_reminders failed")
            return []

    async def get_upcoming(self, user_id: str) -> List[ActionItemSummary]:
        """
        Next 7 days, status 'pending', for a user.
        """
        try:
            now_fn = getattr(time, "utcnow", None)
            now = now_fn() if callable(now_fn) else datetime.utcnow()
            now = _ensure_aware_utc(now)
            future = now + timedelta(days=7)

            query = (
                self.collection
                .where(filter=FieldFilter("user_id", "==", user_id))
                .where(filter=FieldFilter("status", "==", "pending"))
                .where(filter=FieldFilter("datetime", ">=", now))
                .where(filter=FieldFilter("datetime", "<=", future))
                .order_by("datetime")
            )

            summaries: List[ActionItemSummary] = []
            for doc in query.stream():
                data = doc.to_dict()
                summaries.append(
                    ActionItemSummary(
                        id=doc.id,
                        action=data.get("title"),
                        action_type="reminder",
                        time=data.get("datetime"),
                        participants=[],
                        location=None,
                    )
                )
            return summaries
        except Exception:
            logger.exception("[REMINDERS] get_upcoming failed for user %s", user_id)
            return []

    def get_items(
        self,
        user_id: str,
        status: Literal["all", "pending", "completed", "failed"] = "pending",
        from_date: datetime = time.utcnow().replace(microsecond=0),
        to_date: datetime = time.utcnow().replace(microsecond=0) + timedelta(days=7),
    ) -> List[dict]:
        """
        List reminders for a user with optional status/date filters. Returns [{"item_id": ..., ...}]
        """
        try:
            query = self.collection.where(filter=FieldFilter("user_id", "==", user_id))

            if status != "all":
                query = query.where(filter=FieldFilter("status", "==", status))

            if from_date is not None:
                query = query.where(filter=FieldFilter("datetime", ">=", _ensure_aware_utc(from_date)))
            if to_date is not None:
                query = query.where(filter=FieldFilter("datetime", "<=", _ensure_aware_utc(to_date)))

            try:
                query = query.order_by("datetime")
            except Exception:
                pass

            return [{"item_id": doc.id, **doc.to_dict()} for doc in query.stream()]
        except Exception:
            logger.exception("[REMINDERS] get_items failed for user %s", user_id)
            return []
