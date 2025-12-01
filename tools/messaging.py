from __future__ import annotations
from typing import Optional
from tools.base import span_attrs, mark_error, summarize, now_iso, _ok, _fail
from models.app_context import AppCtx
from shared.user import get_user
from store.scheduled_messages_store import ScheduledMessageStore
from models.scheduled_message import ScheduledMessageItem
from shared.time import _parse_iso8601, _to_utc, _user_tz
from store.user import UserStore
from shared.user import userContextDict, normalize_recipient_id
from observability.obs import instrument_io

def _process_contact_message(ctx: AppCtx, action: ScheduledMessageItem) -> dict:
    """
    Process a scheduled message to a contact by chat ID.
    For recipient_chat_id you can pass either:
      - Full chat JID (groups must have a jid)
      - Raw phone number like "9725XXXXXXXX" (with or without '+')
    The tool will normalize phone numbers to full JID automatically.

    Returns: { ok: bool, item_id: str|None, error?: str }
    """
    try:
        user_id = ctx.context.user_id
        
        if action.command not in ("create", "update", "delete"):
            return _fail("unknown_command", {"item_id": None})

        if action.command == "create":
            dt = _parse_iso8601(action.scheduled_time)
            if not dt:
                print("process_contact_message: invalid_datetime_format", action.scheduled_time)
                return _fail("invalid_datetime_format", {"item_id": None})

        elif action.command == "update" and action.scheduled_time is not None:
            if not _parse_iso8601(action.scheduled_time):
                print("process_contact_message: invalid_datetime_format", action.scheduled_time)
                return _fail("invalid_datetime_format", {"item_id": None})

        store = ScheduledMessageStore()
        action.recipient_chat_id = normalize_recipient_id(action.recipient_chat_id)

        if action.command == "create":
            item_id = store.save(user_id=user_id, item=action)
            name = action.recipient_name
            chat_id = action.recipient_chat_id
            user = get_user(user_id)
            contact = user.runtime.contacts.get(name, {})
            contact["phone"] = chat_id.split("@")[0]
            user.runtime.contacts[name] = contact

            UserStore(user_id).save(user)
            userContextDict[user_id] = user

            return _ok({"item_id": item_id})

        if action.command == "update":
            if not (action.item_id or "").strip():
                print("process_contact_message: missing_item_id", action.item_id)
                return _fail("missing_item_id", {"item_id": None})
            allowed_updates = {
                "message": action.message,
                "scheduled_time": action.scheduled_time,
                "status": action.status,
            }
            store.update(item_id=action.item_id, updates=allowed_updates)
            return _ok({"item_id": action.item_id})

        if action.command == "delete":
            if not (action.item_id or "").strip():
                print("process_contact_message: missing_item_id", action.item_id)
                return _fail("missing_item_id", {"item_id": None})
            store.delete(item_id=action.item_id)
            return _ok({"item_id": action.item_id})

        # Shouldn't reach
        print("process_contact_message: unknown_command", action.command)
        return _fail("unknown_command", {"item_id": None})

    except Exception as e:
        mark_error(e, kind="ToolError.process_contact_message", span=s); raise

@instrument_io(
    name="tool.process_contact_message",
    meta={"agent": "tami", "operation": "tool", "tool": "process_contact_message", "schema": "ProcessContactMessage.v1"},
    input_fn=lambda ctx, action: {"user_id": ctx.context.user_id, "action": action},
    output_fn=summarize,
    redact=True,
)
def process_contact_message(ctx: RunContextWrapper[AppCtx], action: ScheduledMessageItem):
    with span_attrs("tool.process_contact_message", agent="tami", operation="tool", tool="process_contact_message") as s:
        s.update(input={"action": action})
        try:
            out = _process_contact_message(ctx=ctx, action=action)
            s.update(output=summarize(out)); return out
        except Exception as e:
            mark_error(e, kind="ToolError.process_contact_message", span=s); raise
