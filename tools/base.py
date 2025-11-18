from __future__ import annotations
from typing import Any, Dict, List, Optional, Literal, Callable
from datetime import datetime

# External deps used by all tools
from agents import function_tool
from observability.obs import span_attrs, instrument_io
from observability.telemetry import mark_error
from models.base_item import BaseActionItem

Json = Dict[str, Any]
SENSITIVE_FIELDS: set[str] = set()

def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def redact(d: dict) -> dict:
    return d

def summarize(out: Any) -> Dict[str, Any]:
    if out is None:
        return {"kind": "none"}
    if hasattr(out, "model_dump"):
        try:
            return {"model": out.__class__.__name__, **out.model_dump(mode="json")}
        except Exception:
            pass
    if isinstance(out, dict):
        return {k: out[k] for k in list(out)[:6]}
    if isinstance(out, list):
        return {"list_len": len(out)}
    return {"repr": str(out)[:200]}

def _fail(msg: str, code: Optional[str] = None):
    return {"ok": False, "item_id": None, "error": msg, "code": code or "bad_request"}

def _ok(item_id: Optional[str]):
    return {"ok": True, "item_id": item_id, "error": None, "code": None}

def _validate(action: BaseActionItem):
    if action.command not in ("create", "update", "delete"):
        return "unknown_command"
    if action.command == "create":
        if not action.title:
            return "missing_title"
        if action.item_type != "task" and not getattr(action, "datetime", None):
            return "missing_datetime"
    if action.command in ("update", "delete") and not action.item_id:
        return "missing_item_id"
    return None

from typing import List, Dict, Tuple
from typing import List, Dict, Tuple

def format_items_for_llm(items: List[dict]) -> Tuple[str, List[Dict]]:
    """
    Format a list of items into an LLM-friendly numbered list (no IDs shown)
    and create an index→id mapping for context (last_tasks_listing).

    Expected `items` structure:
        [
            {"id": "task_17", "title": "...", ...},
            {"id": "task_23", "title": "..."},
            ...
        ]

    Returns:
        formatted_text: str   # what you send back in the assistant message
        mapping: List[dict]   # [{"index": 1, "id": "task_17", "title": "..."}]
    """

    lines: List[str] = []
    mapping: List[Dict] = []

    for idx, item in enumerate(items, start=1):
        item_id = item.get("id") or item.get("item_id")
        title = item.get("title") or item.get("description") or "Untitled"

        # What the user and LLM see: NO IDs, just a numbered list
        # Example: "1. להגיש דו״ח"
        line = f"{idx}. {title}"
        lines.append(line)

        # Index → ID mapping for last_tasks_listing in context
        mapping.append({
            "index": idx,
            "id": item_id,
            "title": title,
        })

    formatted_text = "\n".join(lines)
    return formatted_text, mapping
