from shared import time
from datetime import timedelta
import asyncio
import uuid

from adapters.whatsapp.cloudapi.cloud_api_adapter import CloudAPIAdapter

from store.scheduled_messages_store import ScheduledMessageStore
from store.delivery_mng_store import SendingStatusStore
from store.reminder_item_store import ReminderStore
from store.user import UserStore
from shared.user import send_scheduled_message
# + NEW import
from store.task_item_store import TaskStore  # adjust path/name if different
from observability.obs import span_attrs, mark_error  # NEW

''' echo chat id = '972552534936@c.us' '''

MAX_RETRIES = 5
adapter = CloudAPIAdapter()

# === NEW: outbound-context helpers (must stay in sync with prompt/injection) ===
MAX_RECENT_OUTBOUND = 12
MAX_TEXT_LEN = 160
MAX_TITLE_LEN = 120
MAX_NAME_LEN = 80

def _truncate(s: str, n: int) -> str:
    if not s:
        return ""
    return s if len(s) <= n else s[: max(0, n - 1)] + "…"

def _scope_from_chat_id(target_chat_id: str, owner_user_id: str) -> str:
    if not target_chat_id:
        return ""
    if target_chat_id == owner_user_id:
        return "self"
    if target_chat_id.endswith("@g.us"):
        return "group"
    return "contact"

def _iso(dt) -> str:
    try:
        return dt.isoformat()
    except Exception:
        return str(dt)

def _push_recent_outbound(user_id: str, entry: dict, kind: str):
    """
    Append `entry` to runtime.recent_outbound_messages (newest first, dedup by id),
    cap to MAX_RECENT_OUTBOUND, and update mirrors:
      - last_reminder_sent (for kind='reminder')
      - last_scheduled_message_received (for kind='scheduled_message')
    """
    ustore = UserStore(user_id)
    # Read current
    try:
        snap = ustore.doc_ref.get()
        data = (snap.to_dict() or {})
    except Exception:
        data = {}
    runtime = data.get("runtime", {}) or {}
    existing = runtime.get("recent_outbound_messages") or []

    # Dedup by id and prepend
    filtered = [e for e in existing if e.get("id") != entry.get("id")]
    new_list = [entry] + filtered
    new_list = new_list[:MAX_RECENT_OUTBOUND]

    # Build patch
    patch = {"runtime": {"recent_outbound_messages": new_list}}
    if kind == "reminder":
        patch["runtime"]["last_reminder_sent"] = entry
    elif kind == "scheduled_message":
        patch["runtime"]["last_scheduled_message_received"] = entry

    # Write (merge)
    ustore.doc_ref.set(patch, merge=True)

def _make_outbound_entry(*, kind: str, text: str, sent_at, related_type: str = "",
                        related_id: str = "", related_title: str = "",
                        target_chat_id: str, target_display_name: str = "",
                        owner_user_id: str) -> dict:
    return {
        "id": f"out_{uuid.uuid4().hex}",
        "kind": kind,
        "text": _truncate(text or "", MAX_TEXT_LEN),
        "sent_at": _iso(sent_at),
        "related": {"type": related_type or "", "id": related_id or "",
                    "title": _truncate(related_title or "", MAX_TITLE_LEN)},
        "target": {
            "scope": _scope_from_chat_id(target_chat_id or "", owner_user_id or ""),
            "chat_id": target_chat_id or "",
            "display_name": _truncate(target_display_name or "", MAX_NAME_LEN),
        },
    }

async def trigger_events():
    now = time.utcnow()
    start = now - timedelta(minutes=10)
    end = now

    # --- Reminders handling (self) ---
    reminder_store = ReminderStore()
    reminder_triggerables = reminder_store.query_reminders(start, end)

    if reminder_triggerables and len(reminder_triggerables) > 0:
        print(
            f"🔔 Found {len(reminder_triggerables)} reminders due between "
            f"{start.isoformat()} and {end.isoformat()}"
        )

    for trig in reminder_triggerables:
        status_store = SendingStatusStore(trig["user_id"])
        status_store.create_or_get(trig["item_id"], "reminder")
        status_store.update(trig["item_id"], "reminder", last_status="sending")

        title = (trig.get("title") or "").strip()
        description = (trig.get("description") or "").strip()
        body = title if not description else f"{title}\n{description}"

        # ✅ Trace/span per reminder send
        with span_attrs(
            "scheduler.reminder.send",
            kind="reminder",
            user_id=str(trig["user_id"]),
            item_id=str(trig["item_id"]),
        ) as span:
            try:
                success = await adapter.send_message(trig["user_id"], body)
            except Exception as e:
                print(f"❌ Reminder send exception for {trig['item_id']}: {e}")
                success = False
                # mark as error at tracing level
                mark_error(e, kind="SchedulerError.reminder_send", span=span)

            # attach metadata about the attempt
            span.update(
                metadata={
                    "success": bool(success),
                    "target_chat_id": str(trig["user_id"]),
                    "title": title,
                    "has_description": bool(description),
                    "body_len": len(body or ""),
                }
            )

            if success:
                status_store.reset_retry(trig["item_id"], "reminder")
                status_store.update(trig["item_id"], "reminder", last_status="completed")
                reminder_store.update_status(trig["user_id"], trig["item_id"], "completed")

                entry = _make_outbound_entry(
                    kind="reminder",
                    text=body,
                    sent_at=now,
                    related_type="reminder",
                    related_id=str(trig.get("item_id") or ""),
                    related_title=title,
                    target_chat_id=trig["user_id"],
                    target_display_name="",
                    owner_user_id=trig["user_id"],
                )
                _push_recent_outbound(trig["user_id"], entry, kind="reminder")
            else:
                retries = status_store.increment_retry(trig["item_id"], "reminder")
                status_store.update(trig["item_id"], "reminder", last_status="failed")
                reminder_store.update_status(trig["user_id"], trig["item_id"], "failed")

            await asyncio.sleep(0.2)


    # --- Tasks (due) handling ---
    task_store = TaskStore()
    task_triggerables = task_store.query_tasks_due(start, end)

    if task_triggerables and len(task_triggerables) > 0:
        print(
            f"🔔 Found {len(task_triggerables)} tasks due between "
            f"{start.isoformat()} and {end.isoformat()}"
        )

    for trig in task_triggerables:
        status_store = SendingStatusStore(trig["user_id"])
        status_store.create_or_get(trig["item_id"], "task")
        status_store.update(trig["item_id"], "task", last_status="sending")

        title = (trig.get("title") or "").strip()
        description = (trig.get("description") or "").strip()
        body_lines = [f"✅ משימה לתשומת לבך: {title}"] if title else ["✅ משימה לתשומת לבך"]
        if description:
            body_lines.append(description)
        id = trig["item_id"]
        if id:
            body_lines.append(f"ID: {id}")
        if trig.get("due"):
            due_val = trig["due"]
            due_iso = due_val.isoformat() if hasattr(due_val, "isoformat") else str(due_val)
            body_lines.append(f"תאריך יעד: {due_iso}")
        body = "\n".join(body_lines)

        recipient_chat_id = (trig.get("assignee_chat_id") or trig["user_id"]).strip()
        is_self = (recipient_chat_id == trig["user_id"])
        kind = "reminder" if is_self else "scheduled_message"

        with span_attrs(
            "scheduler.task.send",
            kind="task",
            user_id=str(trig["user_id"]),
            item_id=str(trig["item_id"]),
        ) as span:
            try:
                success = await adapter.send_message(recipient_chat_id, body)
                if success:
                    from agent.sessions import get_session

                    # Same session_id you use for normal runs:
                    session = get_session(trig["user_id"], trig["user_id"])

                    # Append an assistant message to the history
                    await session.add_items([
                        {
                            "role": "assistant",
                            "content": body,
                        }
                    ])

            except Exception as e:
                print(f"❌ Task send exception for {trig['item_id']}: {e}")
                success = False
                mark_error(e, kind="SchedulerError.task_send", span=span)

            span.update(
                metadata={
                    "success": bool(success),
                    "target_chat_id": recipient_chat_id,
                    "is_self": is_self,
                    "title": title,
                    "has_description": bool(description),
                    "body_len": len(body or ""),
                    "due": due_iso if trig.get("due") else None,
                    "item_id": trig["item_id"],
                }
            )

            if success:
                status_store.reset_retry(trig["item_id"], "task")
                status_store.update(trig["item_id"], "task", last_status="completed")
                task_store.update_status(trig["user_id"], trig["item_id"], "completed")

                entry = _make_outbound_entry(
                    kind=kind,
                    text=body,
                    sent_at=now,
                    related_type="task",
                    related_id=str(trig.get("item_id") or ""),
                    related_title=title,
                    target_chat_id=recipient_chat_id,
                    target_display_name=(trig.get("assignee_name") or ""),
                    owner_user_id=trig["user_id"],
                )
                _push_recent_outbound(trig["user_id"], entry, kind=kind)
            else:
                retries = status_store.increment_retry(trig["item_id"], "task")
                status_store.update(trig["item_id"], "task", last_status="failed")
                task_store.update_status(trig["user_id"], trig["item_id"], "failed")

            await asyncio.sleep(0.2)


    # --- ScheduledMessage handling (to contacts/groups) ---
    sched_store = ScheduledMessageStore()
    sched_triggerables = sched_store.query_scheduled_messages(start, end)
    if sched_triggerables and len(sched_triggerables) > 0:
        print(
            f"🔔 Found {len(sched_triggerables)} scheduled messages due between "
            f"{start.isoformat()} and {end.isoformat()}"
        )

    for trig in sched_triggerables:
        status_store = SendingStatusStore(trig["user_id"])
        status_store.create_or_get(trig["item_id"], "scheduled_message")
        status_store.update(trig["item_id"], "scheduled_message", last_status="sending")

        with span_attrs(
            "scheduler.scheduled_message.send",
            kind="scheduled_message",
            user_id=str(trig["user_id"]),
            item_id=str(trig["item_id"]),
        ) as span:
            try:
                if trig["recipient_chat_id"] == trig["user_id"] + "@c.us":
                    success = await adapter.send_message(trig["user_id"], trig.get("message"))
                else:
                    result = await send_scheduled_message(
                        trig["user_id"],
                        trig.get("message"),
                        trig["recipient_chat_id"],
                        trig.get("recipient_name"),
                        trig.get("sender_name"),
                    )
                    success = True
            except Exception as e:
                print(f"❌ Echo fallback send failed for {trig['item_id']}: {e}")
                success = False
                mark_error(e, kind="SchedulerError.scheduled_message_send", span=span)

            span.update(
                metadata={
                    "success": bool(success),
                    "target_chat_id": str(trig.get("recipient_chat_id") or ""),
                    "recipient_name": str(trig.get("recipient_name") or ""),
                    "message_len": len(str(trig.get("message") or "")),
                }
            )

            if success:
                status_store.reset_retry(trig["item_id"], "scheduled_message")
                status_store.update(trig["item_id"], "scheduled_message", last_status="completed")
                sched_store.update_status(trig["item_id"], "completed")

                entry = _make_outbound_entry(
                    kind="scheduled_message",
                    text=str(trig.get("message") or ""),
                    sent_at=now,
                    related_type="message",
                    related_id=str(trig.get("item_id") or ""),
                    related_title=str(trig.get("title") or ""),
                    target_chat_id=str(trig.get("recipient_chat_id") or ""),
                    target_display_name=str(trig.get("recipient_name") or ""),
                    owner_user_id=trig["user_id"],
                )
                _push_recent_outbound(trig["user_id"], entry, kind="scheduled_message")
            else:
                sched_store.update_status(trig["item_id"], "failed")

            await asyncio.sleep(0.2)

async def wait_or_stop(stop_event: asyncio.Event, timeout: float) -> None:
    if stop_event.is_set():
        return
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        pass

async def trigger_events_loop(stop_event: asyncio.Event):
    """Runs trigger_events repeatedly until stop_event is set."""
    while not stop_event.is_set():
        try:
            await trigger_events()
        except Exception as e:
            print(f"Loop error: {e}")
        await wait_or_stop(stop_event, 10)

if __name__ == "__main__":
    asyncio.run(trigger_events())
