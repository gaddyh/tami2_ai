# tami_dummy_tools.py
from typing import Dict, Any, List
from datetime import datetime
import uuid
from pydantic import BaseModel 

from models.task_item import TaskItem
from models.get_query import GetItemsQuery

from tools.task import _process_task
from tools.get_items import _get_items
from shared.user import get_user
# -------------------------------------------------
# In-memory demo DB: project → {"tasks": [...], "reminders": [...]}
# -------------------------------------------------
DB: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}


def _project_store(state: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Return the per-project store (tasks/reminders) from the global DB."""
    project = state.get("project") or "default"
    store = DB.setdefault(project, {"tasks": [], "reminders": []})
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

    print("get_items_tool", user_id, "tasks", query.status, query.start_date, query.end_date)
    try:
        # _get_items already returns {ok, items, error, code}
        return _get_items(user_id, "tasks", query.status, query.start_date, query.end_date)

    except Exception as e:
        return {
            "ok": False,
            "items": [],
            "error": str(e),
            "code": None,
        }


def process_task_tool(args: TaskItem | Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    task = _as_task_item(args)
    ctx = state.get("context")
    if not ctx:
        raise ValueError("ctx not found in state")

    user_id = ctx.get("user_id")
    if not user_id:
        raise ValueError("user_id not found in ctx")

    # -------------------------------------
    # 1) Auto resolve item_id from last_tasks_listing
    # -------------------------------------
    if task.command in ("delete", "complete") and not task.item_id:
        user = get_user(user_id)
        listing = getattr(getattr(user, "runtime", None), "last_tasks_listing", None)

        if listing:
            match = next(
                (it for it in listing["items"] if it["title"] == task.title),
                None
            )
            if match:
                task.item_id = match["item_id"]

    # -------------------------------------
    # 2) Now call real process_task
    # -------------------------------------
    return _process_task(user_id, task)
