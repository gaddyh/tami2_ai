# tami_dummy_tools.py
from typing import Dict, Any, List
from datetime import datetime
import uuid
from pydantic import BaseModel 

from models.task_item import TaskItem
from models.get_query import GetItemsQuery

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
    item_type = query.item_type

    store = _project_store(state)

    if item_type == "task":
        all_items = store["tasks"]
    elif item_type == "reminder":
        all_items = store["reminders"]
    else:
        all_items = []

    # Very simple status filter for demo
    if hasattr(query, "status") and query.status != "all":
        status = query.status
        items = [it for it in all_items if it.get("status") == status]
    else:
        items = list(all_items)

    # ignore focus/start_date/end_date for the demo

    return {
        "status": "ok",
        "item_type": item_type,
        "items": items,
        "count": len(items),
    }


def process_task_tool(
    args: TaskItem | Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    task = _as_task_item(args)

    store = _project_store(state)
    tasks: List[Dict[str, Any]] = store["tasks"]

    command = task.command
    item_id = task.item_id or f"task_{uuid.uuid4().hex[:8]}"

    if command == "create":
        t = {
            "item_id": item_id,
            "title": task.title,
            "description": task.description,
            "due": task.due,
            "status": task.status,      # "open" by default
            "focus": task.focus,
            "created_at": _now_iso(),
        }
        tasks.append(t)
        return {"status": "ok", "command": command, "task": t}

    elif command == "update":
        for t in tasks:
            if t["item_id"] == item_id:
                # minimal patch logic for demo
                if task.title:
                    t["title"] = task.title
                if task.description is not None:
                    t["description"] = task.description
                if task.due is not None:
                    t["due"] = task.due
                if task.status:
                    t["status"] = task.status
                if task.focus:
                    t["focus"] = task.focus
                return {"status": "ok", "command": command, "task": t}
        # not found
        return {
            "status": "error",
            "command": command,
            "error": "task_not_found",
            "item_id": item_id,
        }

    elif command == "delete":
        before = len(tasks)
        tasks[:] = [t for t in tasks if t["item_id"] != item_id]
        deleted = before - len(tasks)
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
