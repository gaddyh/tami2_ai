from __future__ import annotations
from typing import Any, Dict, List, Optional, Literal
from store.user import UserStore
from tools.base import function_tool, span_attrs, mark_error, redact, summarize, _fail, _ok, format_items_for_llm
from models.app_context import AppCtx, LastTasksListing, LastTaskEntry
from agents import RunContextWrapper
from store.reminder_item_store import ReminderStore
from store.task_item_store import TaskStore
from store.scheduled_messages_store import ScheduledMessageStore
from store.google_calendar_store import GoogleCalendarStore
from datetime import datetime, timezone
from shared.time import _parse_iso8601, _to_utc, _user_tz
from observability.obs import instrument_io
from shared.user import get_user
from models.user import userContextDict
from store.user import UserStore
from shared.time import utcnow  # or datetime.now(timezone.utc) – whatever you use

def _build_last_tasks_listing(tasks: list[dict]) -> LastTasksListing:
    return LastTasksListing(
        generated_at=utcnow(),
        items=[
            LastTaskEntry(
                index=i + 1,
                item_id=str(t["id"]),          # adapt field name if needed
                title=str(t.get("title", "")), # optional but nice to have
            )
            for i, t in enumerate(tasks)
        ],
    )

def _get_items(
    ctx: RunContextWrapper[AppCtx],
    item_type: Literal["reminders", "tasks", "events", "scheduled_messages", "action_items"],
    status: Literal["all", "pending", "completed"] = "pending",
    from_date: Optional[datetime | str] = None,
    to_date: Optional[datetime | str] = None,
) -> dict:
    """
    Get reminders, tasks, or events filtered by status and/or date range.
    Returns: { ok: bool, items: list, error?: str }
    """
    user_id = ctx.context.user_id
    user_tz = _user_tz(user_id)

    # ---- coerce possible string dates -> datetime, then to UTC ----
    def _coerce(dt):
        if dt is None:
            return None
        if isinstance(dt, str):
            return _parse_iso8601(dt)
        return dt

    from_dt = _coerce(from_date)
    to_dt = _coerce(to_date)

    from_date_utc = _to_utc(from_dt, user_tz) if from_dt else None
    to_date_utc = _to_utc(to_dt, user_tz) if to_dt else None

    if item_type == "events" and status == "pending" and not from_date_utc and not to_date_utc:
        from datetime import timedelta
        now_utc = datetime.now(timezone.utc)
        from_date_utc = now_utc
        to_date_utc = now_utc + timedelta(days=30)

    try:
        if item_type == "reminders":
            store = ReminderStore()
            items = store.get_items(user_id=user_id, status=status, from_date=from_date_utc, to_date=to_date_utc)
        elif item_type == "tasks":
            store = TaskStore()
            items = store.get_items(user_id=user_id, status=status, from_date=from_date_utc, to_date=to_date_utc)
            formatted_text, mapping = format_items_for_llm(items)
            last_tasks_listing = {
                "generated_at": utcnow().isoformat(),
                "items": [
                    {
                        "index": m["index"],
                        "item_id": m["id"],
                        "title": m["title"],
                    }
                    for m in mapping
                ],
            }
            user = get_user(user_id)
            if user and getattr(user, "runtime", None):
                user.runtime.last_tasks_listing = last_tasks_listing
                UserStore(user_id).save(user)
                userContextDict[user_id] = user
            
            items = formatted_text
        elif item_type == "scheduled_messages":
            store = ScheduledMessageStore()
            items = store.get_items(user_id=user_id, status=status, from_date=from_date_utc, to_date=to_date_utc)
        elif item_type == "events":
            cal = GoogleCalendarStore()
            items = cal.get_items(user_id=user_id, from_date=from_date_utc, to_date=to_date_utc, status=status)

        return _ok({"items": items})

    except Exception:
        return _fail("internal_error", {"items": []})

@function_tool(strict_mode=True)
@instrument_io(
    name="tool.get_items",
    meta={"agent": "tami", "operation": "tool", "tool": "get_items", "schema": "GetItems.v1"},
    input_fn=lambda ctx, item_type, status, from_date, to_date: {"user_id": ctx.context.user_id, "item_type": item_type, "status": status, "from_date": from_date, "to_date": to_date},
    output_fn=summarize,
    redact=True,
)
def get_items(ctx: RunContextWrapper[AppCtx],  item_type: Literal["reminders", "tasks", "events", "scheduled_messages", "action_items"],
    status: Literal["all", "pending", "completed"] = "pending",
    from_date: Optional[datetime | str] = None,
    to_date: Optional[datetime | str] = None,):
    with span_attrs("tool.get_items", agent="tami", operation="tool", tool="get_items") as s:
        s.update(input={"filters": redact({"item_type": item_type, "status": status, "from_date": from_date, "to_date": to_date})})
        try:
            out = _get_items(ctx=ctx, item_type=item_type, status=status, from_date=from_date, to_date=to_date)
            s.update(output={"count": len(out) if isinstance(out, list) else None, **summarize(out)})
            return out
        except Exception as e:
            mark_error(e, kind="ToolError.get_items", span=s); raise


