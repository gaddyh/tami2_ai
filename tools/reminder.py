from __future__ import annotations
from typing import Dict, Any
from models.reminder_item import ReminderItem
from tools.base import function_tool, instrument_io, summarize, _validate, _ok, _fail
from agents import RunContextWrapper
from store.reminder_item_store import ReminderStore
from models.app_context import AppCtx

@function_tool(strict_mode=True)
@instrument_io(
    name="tool.process_reminder",
    meta={"agent": "tami", "operation": "tool", "tool": "process_reminder", "schema": "ReminderItem.v1"},
    input_fn=lambda ctx, reminder: {"user_id": ctx.context.user_id, "reminder": reminder},
    output_fn=summarize,
    redact=True,
)
def process_reminder(ctx: RunContextWrapper[AppCtx], reminder: ReminderItem ) -> Dict[str, Any]:
    user_id = ctx.context.user_id
    print("user_id", user_id)
    store = ReminderStore()

    # Enforce item_id on update/delete at the tool layer
    if reminder.command in ("update", "delete") and not reminder.item_id:
        return _fail("missing_item_id", code="validation_error")

    err = _validate(reminder)
    if err:
        return _fail(err)

    # IMPORTANT: pass the original datetime through (str or datetime).
    # The store converts it to aware UTC, treating naive as Asia/Jerusalem.
    dt_in = getattr(reminder, "datetime", None)
    op_id = getattr(reminder, "op_id", None)

    if reminder.command == "create":
        item_id = store.create_reminder(
            user_id=user_id,
            title=reminder.title,
            description=reminder.description,
            dt=dt_in,           # <- no pre-stringify; store handles tz/UTC
            op_id=op_id,
        )
        return _ok(item_id)

    if reminder.command == "update":
        updated = store.update_reminder(
            user_id=user_id,
            item_id=reminder.item_id,
            title=reminder.title,
            description=reminder.description,
            dt=dt_in,           # <- same here
            status=reminder.status,
        )
        if not updated:
            return _fail("not_found", code="not_found")
        return _ok(reminder.item_id)

    if reminder.command == "delete":
        deleted = store.delete_reminder(user_id=user_id, item_id=reminder.item_id)
        if not deleted:
            return _fail("not_found", code="not_found")
        return _ok(reminder.item_id)

    return _fail("unknown_command")

