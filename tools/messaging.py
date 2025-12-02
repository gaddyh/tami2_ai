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

def _process_scheduled_message(
    user_id: str,
    action: ScheduledMessageItem,
) -> Dict[str, Any]:

    try:
        
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
            if name:
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
        print(f"Error in process_scheduled_message: {e}")

        #import traceback
        #traceback.print_exc()
        #raise  # <--- let it propagate so you get a full stack trace
        return _fail(f"_process_scheduled_message failed for user {user_id}. error: {str(e)}", {"item_id": None})

