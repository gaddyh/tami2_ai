# tami_dummy_tools.py
from typing import Dict, Any, List
from datetime import datetime, timedelta
import uuid

from pydantic import BaseModel  # <-- add this
from models.reminder_item import ReminderItem
from models.task_item import TaskItem, BulkTasksAction
from models.get_query import GetItemsQuery

# -------------------------------------------------
# In-memory demo DB: project → per-project store
# -------------------------------------------------
# We keep tasks/reminders as before and add messages/chat_history/contacts
DB: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}


def _project_store(state: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Return the per-project store (tasks/reminders/...) from the global DB."""
    project = state.get("project") or "default"
    store = DB.setdefault(
        project,
        {
            "tasks": [],
            "reminders": [],
            "messages": [],       # for scheduled/queued messages
            "chat_history": [],   # fake chat history for search
            "contacts": [],       # fake contacts for recipient candidates
        },
    )
    return store


def _now_iso() -> str:
    return datetime.now().isoformat()


# ---------- helpers ----------

def _as_get_items_query(args: GetItemsQuery | Dict[str, Any]) -> GetItemsQuery:
    if isinstance(args, BaseModel):
        return args
    return GetItemsQuery(**args)


def _as_task_item(args: TaskItem | Dict[str, Any]) -> TaskItem:
    if isinstance(args, BaseModel):
        return args
    return TaskItem(**args)


def _as_bulk_tasks_action(args: BulkTasksAction | Dict[str, Any]) -> BulkTasksAction:
    if isinstance(args, BaseModel):
        return args
    return BulkTasksAction(**args)


def _as_reminder_item(args: ReminderItem | Dict[str, Any]) -> ReminderItem:
    if isinstance(args, BaseModel):
        return args
    return ReminderItem(**args)


# =================================================
#  COMMS TOOLS — DUMMY IMPLEMENTATIONS FOR TESTING
# =================================================

def get_candidates_recipient_info(
    args: Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Dummy recipient lookup.

    - Uses a small in-memory 'contacts' list per project.
    - Optionally filters by a hint found in state (recipient_name / context).
    - Returns a candidates list similar to what your interrupt chooser expects.
    """
    store = _project_store(state)

    # Seed fake contacts once
    if not store["contacts"]:
        store["contacts"].extend(
            [
                {
                    "name": "אמא",
                    "chat_id": "972500000001@c.us",
                    "type": "family",
                },
                {
                    "name": "מיכל",
                    "chat_id": "972500000002@c.us",
                    "type": "friend",
                },
                {
                    "name": "גל",
                    "chat_id": "972500000003@c.us",
                    "type": "work",
                },
            ]
        )

    # Try to infer a hint from state
    hint = (
        state.get("recipient_name")
        or state.get("context", {}).get("recipient_name")
        or state.get("context", {}).get("recipient_hint")
        or state.get("input_text")
        or ""
    )

    candidates = store["contacts"]
    if hint:
        h = hint.casefold()
        filtered = [
            c for c in candidates
            if h in c["name"].casefold()
        ]
        if filtered:
            candidates = filtered

    # Add a naive score just to make the shape richer
    for c in candidates:
        c.setdefault("score", 0.9 if hint and hint in c["name"] else 0.5)

    return {
        "status": "ok",
        "hint": hint,
        "candidates": candidates,
        "count": len(candidates),
    }


def process_scheduled_message(
    args: Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Dummy scheduled-message processor.

    - Looks at store["messages"].
    - Treats messages with:
        status == "pending" and scheduled_at <= now
      as 'due'.
    - Marks them as 'sent' and sets sent_at.
    """
    store = _project_store(state)
    messages = store["messages"]

    now = datetime.now()
    processed_ids: List[str] = []

    for m in messages:
        if m.get("status") != "pending":
            continue

        scheduled_at = m.get("scheduled_at")
        if not scheduled_at:
            continue

        try:
            when = datetime.fromisoformat(scheduled_at)
        except Exception:
            # ignore malformed dates in dummy
            continue

        if when <= now:
            m["status"] = "sent"
            m["sent_at"] = _now_iso()
            processed_ids.append(m.get("item_id") or "")

    return {
        "status": "ok",
        "processed_count": len(processed_ids),
        "processed_ids": processed_ids,
    }


def search_chat_history(
    args: Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Dummy chat-history search.

    Args (dict, free-form for now):
      - query: str (optional)
      - limit: int (optional, default 20)

    Behavior:
      - Seeds a small fake chat history on first use.
      - If query is provided, filters by substring over 'text'.
      - Returns the last N matching messages (limit).
    """
    query = (args or {}).get("query", "") or ""
    limit = int((args or {}).get("limit", 20) or 20)

    store = _project_store(state)
    history = store["chat_history"]

    # Seed fake history once
    if not history:
        history.extend(
            [
                {
                    "message_id": "m1",
                    "chat_id": "972500000001@c.us",
                    "sender": "me",
                    "text": "אני בדרך",
                    "timestamp": _now_iso(),
                },
                {
                    "message_id": "m2",
                    "chat_id": "972500000002@c.us",
                    "sender": "מיכל",
                    "text": "הפגישה תידחה בשעה",
                    "timestamp": _now_iso(),
                },
                {
                    "message_id": "m3",
                    "chat_id": "972500000003@c.us",
                    "sender": "גל",
                    "text": "תשלח לי את הסיכום של הפגישה האחרונה",
                    "timestamp": _now_iso(),
                },
            ]
        )

    items: List[Dict[str, Any]] = history
    if query:
        q = query.casefold()
        items = [
            m for m in history
            if q in (m.get("text", "").casefold())
        ]

    # Return the last N
    items = items[-limit:]

    return {
        "status": "ok",
        "query": query,
        "items": items,
        "count": len(items),
    }
