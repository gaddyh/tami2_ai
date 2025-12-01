# tami_dummy_tools.py
from typing import Dict, Any, List
from datetime import datetime
import uuid

from pydantic import BaseModel
from models.reminder_item import ReminderItem
from models.task_item import TaskItem, BulkTasksAction
from models.event_item import EventItem
from models.base_item import ItemStatus

# -------------------------------------------------
# In-memory demo DB: project → {"tasks": [...], "reminders": [...], "events": [...]}
# -------------------------------------------------
DB: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}


from typing import Optional, Union, Literal
from pydantic import BaseModel, Field

class GetItemsQuery(BaseModel):
    item_type: Literal["event"] = Field(
        "event",
        description=(
            "Always 'event'. Specifies which item type to return. "
            "Used to distinguish events from tasks or other item types."
        ),
    )

    status: Union[ItemStatus, Literal["all"]] = Field(
        "open",
        description=(
            "Event status filter. "
            "'open' = active events, 'completed' = finished ones, "
            "'deleted' = soft-deleted events, 'all' = no filtering."
        ),
    )

    start_date: Optional[str] = Field(
        None,
        description=(
            "Optional inclusive start date filter (YYYY-MM-DD). "
            "Only events starting on or after this date are returned."
        ),
    )

    end_date: Optional[str] = Field(
        None,
        description=(
            "Optional exclusive end date filter (YYYY-MM-DD). "
            "Only events starting before this date are returned."
        ),
    )

    limit: int = Field(
        100,
        description="Maximum number of events to return (default = 100).",
    )

    model_config = {
        "extra": "forbid",
    }

def _project_store(state: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Return the per-project store (tasks/reminders/events) from the global DB.
    Ensures all three lists exist.
    """
    project = state.get("project") or "default"
    store = DB.setdefault(project, {"tasks": [], "reminders": [], "events": []})
    # In case an older version created this without 'events'
    store.setdefault("events", [])
    return store


def _now_iso() -> str:
    return datetime.now().isoformat()


# ---------- helpers ----------

def _as_get_items_query(args: GetItemsQuery | Dict[str, Any]) -> GetItemsQuery:
    if isinstance(args, BaseModel):
        return args
    return GetItemsQuery(**args)


def _as_event_item(args: EventItem | Dict[str, Any]) -> EventItem:
    if isinstance(args, BaseModel):
        print("_as_event_item BaseModel item\n\n\n", args)
        return args
    print("_as_event_item Dict item\n\n\n", args)
    return EventItem(**args)


def _as_bulk_tasks_action(args: BulkTasksAction | Dict[str, Any]) -> BulkTasksAction:
    if isinstance(args, BaseModel):
        return args
    return BulkTasksAction(**args)


def _as_reminder_item(args: ReminderItem | Dict[str, Any]) -> ReminderItem:
    if isinstance(args, BaseModel):
        return args
    return ReminderItem(**args)


# ---------- PRIMARY: Events & Tasks ----------

def get_items_tool(
    args: GetItemsQuery | Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Generic get-items tool used by different domain agents.
    For the events agent, item_type will be 'event'.
    """
    query = _as_get_items_query(args)
    item_type = query.item_type

    store = _project_store(state)

    if item_type == "task":
        all_items = store["tasks"]
    elif item_type == "reminder":
        all_items = store["reminders"]
    elif item_type == "event":
        all_items = store["events"]
    else:
        # Unknown type → empty result, but keep status "ok"
        all_items = []

    # Very simple status filter for demo
    if hasattr(query, "status") and getattr(query, "status") != "all":
        status = query.status
        items = [it for it in all_items if it.get("status") == status]
    else:
        items = list(all_items)

    # For the demo, ignore focus/start_date/end_date

    return {
        "status": "ok",
        "item_type": item_type,
        "items": items,
        "count": len(items),
    }


def process_event_tool(
    args: EventItem | Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Very simple in-memory implementation of process_event.
    Ignores most calendar semantics; just stores basic event fields.
    """
    event = _as_event_item(args)

    store = _project_store(state)
    events: List[Dict[str, Any]] = store["events"]

    command = event.command
    item_id = event.item_id or f"event_{uuid.uuid4().hex[:8]}"

    if command == "create":
        e = {
            "item_id": item_id,
            "title": event.title,
            "description": event.description,
            # time / date fields
            "datetime": event.datetime,
            "end_datetime": event.end_datetime,
            "date": event.date,
            "end_date": event.end_date,
            "all_day": event.all_day,
            # metadata
            "location": event.location,
            "status": getattr(event, "status", "open"),
            "created_at": _now_iso(),
        }
        events.append(e)
        return {"status": "ok", "command": command, "event": e}

    elif command == "update":
        for e in events:
            if e["item_id"] == item_id:
                # minimal patch logic for demo
                if event.title:
                    e["title"] = event.title
                if event.description is not None:
                    e["description"] = event.description
                if event.datetime is not None:
                    e["datetime"] = event.datetime
                if event.end_datetime is not None:
                    e["end_datetime"] = event.end_datetime
                if event.date is not None:
                    e["date"] = event.date
                if event.end_date is not None:
                    e["end_date"] = event.end_date
                if event.all_day is not None:
                    e["all_day"] = event.all_day
                if event.location is not None:
                    e["location"] = event.location
                if getattr(event, "status", None):
                    e["status"] = event.status
                return {"status": "ok", "command": command, "event": e}

        # not found
        return {
            "status": "error",
            "command": command,
            "error": "event_not_found",
            "item_id": item_id,
        }

    elif command == "delete":
        before = len(events)
        events[:] = [e for e in events if e["item_id"] != item_id]
        deleted = before - len(events)
        return {
            "status": "ok",
            "command": command,
            "item_id": item_id,
            "deleted": deleted,
        }

    # Fallback for unknown command
    return {
        "status": "error",
        "command": command,
        "error": "unknown_command",
        "item_id": item_id,
    }


from typing import Dict, Any

def get_candidates_recipient_info(
    args: Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Dummy recipient lookup.

    - Uses a small in-memory 'contacts' list per project.
    - Optionally filters by a hint (name) from args/state.
    - Returns a candidates list similar to what your interrupt chooser expects.
    """
    store = _project_store(state)

    # Always have a contacts list
    contacts = store.setdefault("contacts", [])

    # Seed fake contacts once
    if not contacts:
        contacts.extend(
            [
                {
                    "name": "אמא",
                    "chat_id": "972500000001@c.us",
                    "type": "family",
                },
                {
                    "name": "מעוז",
                    "chat_id": "972500000002@c.us",
                    "type": "friend",
                    "email": "muoz@gmail.com",
                },
                {
                    "name": "גל ליס",
                    "chat_id": "972500000003@c.us",
                    "type": "work",
                    "email": "gal@gmail.com",
                },
            ]
        )

    # Prefer explicit name from args, then fall back to state / text
    hint = (
        args.get("name")
        or state.get("recipient_name")
        or state.get("context", {}).get("recipient_name")
        or state.get("context", {}).get("recipient_hint")
        or state.get("input_text")
        or ""
    )

    candidates = contacts
    if hint:
        h = hint.casefold()
        filtered = [
            c for c in candidates
            if h in c.get("name", "").casefold()
        ]
        if filtered:
            candidates = filtered

    # Add a naive score just to make the shape richer
    if hint:
        h = hint.casefold()
        for c in candidates:
            name_cf = c.get("name", "").casefold()
            c.setdefault("score", 0.9 if h in name_cf else 0.5)
    else:
        for c in candidates:
            c.setdefault("score", 0.5)

    return {
        "status": "ok",
        "hint": hint,
        "candidates": candidates,
        "count": len(candidates),
    }
