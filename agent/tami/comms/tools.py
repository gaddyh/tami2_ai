# tami_dummy_tools.py
from typing import Dict, Any, List
from datetime import datetime, timedelta
import uuid

from pydantic import BaseModel  # <-- add this
from models.reminder_item import ReminderItem
from models.task_item import TaskItem, BulkTasksAction
from tools.recipients import _get_candidates_recipient_info
from tools.messaging import _process_scheduled_message
from models.scheduled_message import ScheduledMessageItem
from models.base_item import ItemStatus
from tools.get_items import _get_items
from typing import Literal, Union, Optional

class GetItemsQuery(BaseModel):
    item_type: Literal["scheduled_messages"]
    status: Union[ItemStatus, Literal["all"]] = "open"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    limit: int = 100

    model_config = {
        "extra": "forbid",
    }
DB: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

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

def get_candidates_recipient_info(
    args: Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    #print("get_candidates_recipient_info state", state)
    #print("get_candidates_recipient_info args", args)

    ctx = state.get("context")
    if not ctx:
        raise ValueError("ctx not found in state")

    user_id = ctx.get("user_id")
    if not user_id:
        raise ValueError("user_id not found in ctx")

    # --------------------------
    # Extract raw query STRING
    # --------------------------
    raw_name = args.get("name") or args.get("name_hint") or ""
    if not isinstance(raw_name, str):
        raise ValueError(f"get_candidates_recipient_info expected string for name/name_hint, got {type(raw_name)}")

    # --------------------------
    # Call the real resolver
    # --------------------------
    return _get_candidates_recipient_info(
        user_id=user_id,
        name=raw_name,
    )


def process_scheduled_message(
    args: Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    
    ctx = state.get("context")
    if not ctx:
        raise ValueError("ctx not found in state")

    user_id = ctx.get("user_id")
    if not user_id:
        raise ValueError("user_id not found in ctx")

    action = ScheduledMessageItem(**args)
    action.status = "open"
    return _process_scheduled_message(user_id=user_id, action=action)
 
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

def get_items_tool(
    args: GetItemsQuery | Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    query = _as_get_items_query(args)
    ctx = state.get("context")
    if not ctx:
        raise ValueError("ctx not found in state")

    user_id = ctx.get("user_id")
    if not user_id:
        raise ValueError("user_id not found in ctx")

    print("get_items_tool", user_id, "scheduled_messages", query.status, query.start_date, query.end_date)
    try:
        # _get_items already returns {ok, items, error, code}
        return _get_items(user_id, "scheduled_messages", query.status, query.start_date, query.end_date)

    except Exception as e:
        return {
            "ok": False,
            "items": [],
            "error": str(e),
            "code": None,
        }

