

from models.input import In
from agent.tami.graph import build_tami_router_app, handle_tami_turn
from agent.linear_flow.state import LinearAgentState
import time
from datetime import datetime

def to_iso(dt):
    return dt.isoformat() if isinstance(dt, datetime) else dt

app = build_tami_router_app()

def process_input(inp: In)->str:
    start_time = time.time()
    state: LinearAgentState = {
        "input_text": inp.text,
        "context": {
            "user_id": inp.user_id,
            "user_name": inp.user_name,
            "thread_id": inp.thread_id,
            "chat_id": inp.chat_id,
            "source": inp.source,
            "category": inp.category,
            "text": inp.text,
            "input_id": inp.input_id,
            "idempotency_key": inp.idempotency_key,
            "source_ids": inp.source_ids,
            "attachments": inp.attachments,
            "metadata": inp.metadata,
            "reply": inp.reply,
            "locale": inp.locale,
            "tz": inp.tz,
            "current_datetime": to_iso(inp.current_datetime),
            "received_at": to_iso(inp.received_at),
            "redacted": inp.redacted,
        },
    }
    res = handle_tami_turn(app, inp.thread_id, inp.text, base_state=state)
    end_time = time.time()
    print(f"turn took {end_time - start_time:.2f}s")
    return res
