from shared import time
from datetime import timedelta
import asyncio
import uuid

from adapters.whatsapp.cloudapi.cloud_api_adapter import CloudAPIAdapter

from store.task_item_store import TaskStore  # adjust path/name if different
from observability.obs import span_attrs, mark_error  # NEW
from tools.base import format_items_for_llm

adapter = CloudAPIAdapter()

MAX_TEXT_LEN = 160
MAX_TITLE_LEN = 120
MAX_NAME_LEN = 80

async def handle_daily_tasks_digest(user_id: str):
    task_store = TaskStore()
    # 1) Fetch open tasks
    open_tasks = task_store.get_items(
        user_id=user_id,
        status="pending",   # adjust if your API differs
    )

    if not open_tasks:
        body = "בוקר טוב 🙂 אין לך משימות פתוחות כרגע."
    else:
        list_text, mapping = format_items_for_llm(open_tasks)

        count = len(open_tasks)
        body = (
            f"בוקר טוב 🙂 יש לך {count} משימות פתוחות:\n"
            f"{list_text}\n\n"
            "רוצה לסגור חלק מהמשימות או לעדכן משהו?"
        )

    with span_attrs(
        "scheduler.daily_tasks_digest.send",
        kind="daily_tasks_digest",
        user_id=str(user_id),
    ) as span:
        try:
            success = await adapter.send_message(user_id, body)

            if success:
                # 2) Update session so agent sees this message in history
                from agent.sessions import get_session
                session = get_session(user_id, user_id)

                await session.add_items([{
                    "role": "assistant",
                    "content": body,
                }])

        except Exception as e:
            success = False
            mark_error(e, kind="SchedulerError.daily_tasks_digest", span=span)

        span.update(
            metadata={
                "success": bool(success),
                "target_chat_id": user_id,
                "open_task_count": len(open_tasks),
                "body_len": len(body or ""),
            }
        )

        await asyncio.sleep(0.2)
