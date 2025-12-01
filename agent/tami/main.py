from models.input import In
from agent.tami.graph import build_tami_router_app, handle_tami_turn
from agent.linear_flow.state import LinearAgentState
import time
from datetime import datetime
import uuid
from models.input import Source, Category
from shared.time import utcnow, now_iso_in_tz

def to_iso(dt):
    return dt.isoformat() if isinstance(dt, datetime) else dt

app = build_tami_router_app()


def process_input(inp: In) -> str:
    start_time = time.time()

    # -----------------------------
    # Build base LinearAgentState
    # -----------------------------
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

    # -----------------------------
    # Run Tami turn
    # -----------------------------
    result = handle_tami_turn(app, inp.thread_id, inp.text, base_state=state)
    end_time = time.time()
    print(f"turn took {end_time - start_time:.2f}s")

    status = result.get("status")
    graph_state = result.get("state") or {}

    # -----------------------------
    # Decide what to send back
    # -----------------------------
    response: str | None = None
    followup: str | None = None

    if status == "ok":
        # Normal completed turn: responder wrote into graph_state
        response = graph_state.get("response")
        followup = graph_state.get("followup_message")
    elif status == "interrupt":
        # Follow-up interrupt: question is on the Interrupt payload
        intr = result.get("interrupt")
        if intr is not None:
            value = getattr(intr, "value", {}) or {}
            followup = value.get("question")

    if followup:
        outgoing = followup
    elif response:
        outgoing = response
    else:
        outgoing = "משהו השתבש, לא התקבלה תשובה."

    # Debug print (optional, like eval)
    print("=== Tami Turn Output ===")
    print("status:", status)
    print("graph_state:", graph_state)
    print("outgoing_message:", outgoing)

    return outgoing


if __name__ == "__main__":
    msg = process_input(
        In(
            thread_id="tami-demo-thread-1" + uuid.uuid4().hex,
            text="תקבע פגישה קבועה, בימי שני ב14, עם גל ליס ומעוז",
            user_id="user_id",
            user_name="user_name",
            source=Source.WHATSAPP,
            category=Category.USER_REQUEST,
            input_id=uuid.uuid4().hex,
            idempotency_key=uuid.uuid4().hex,
            tz="Asia/Jerusalem",
            locale="he",
            current_datetime=now_iso_in_tz("Asia/Jerusalem"),
            received_at=utcnow(),
            redacted=False,
        )
    )
    print("=== Final message to user ===")
    print(msg)
