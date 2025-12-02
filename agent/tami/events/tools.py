# tami_dummy_tools.py
from typing import Dict, Any, List
from datetime import datetime
import uuid

from pydantic import BaseModel
from models.reminder_item import ReminderItem
from models.task_item import TaskItem, BulkTasksAction
from models.event_item import EventItem
from models.base_item import ItemStatus
from tools.recipients import _get_candidates_recipient_info
from tools.process_event import _process_event
from tools.get_items import _get_items
from shared.user import get_user
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
    query = _as_get_items_query(args)
    ctx = state.get("context")
    if not ctx:
        raise ValueError("ctx not found in state")

    user_id = ctx.get("user_id")
    if not user_id:
        raise ValueError("user_id not found in ctx")

    print("get_items_tool", user_id, "events", query.status, query.start_date, query.end_date)
    try:
        # _get_items already returns {ok, items, error, code}
        return _get_items(user_id, "events", query.status, query.start_date, query.end_date)

    except Exception as e:
        return {
            "ok": False,
            "items": [],
            "error": str(e),
            "code": None,
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
    ctx = state.get("context")
    if not ctx:
        raise ValueError("ctx not found in state")

    user_id = ctx.get("user_id")
    if not user_id:
        raise ValueError("user_id not found in ctx")

    return _process_event(user_id, event)


from typing import Dict, Any

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
