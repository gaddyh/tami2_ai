# demo_tami_router_seq.py

from agent.tami.graph import build_tami_router_app
from agent.linear_flow.state import LinearAgentState
from agent.tami.graph import handle_tami_turn
import uuid
import time
def run_message(app, thread_id, text):
    state: LinearAgentState = {
        "input_text": text,
        "context": {},
    }

    print("\n==============================")
    print("USER:", text)
    print("==============================")

    start_time = time.time()
    res = handle_tami_turn(app, thread_id, text, base_state=state)
    end_time = time.time()
    print(f"turn took {end_time - start_time:.2f}s")

    if res["status"] == "interrupt":
        interrupt_payload = res["interrupt"].value
        result = interrupt_payload["question"]
        print("FOLLOWUP:", result)
    else:
        state = res["state"]
        result = state
        print("→ final response:", result.get("response"))
    return result


def main():
    app = build_tami_router_app()
    thread_id = "tami-demo-thread-1" + uuid.uuid4().hex

    messages = [
        "בעוד שעה תזכיר לי להתקשר לבנק",
           "תזכיר לי מחר לשלם ארנונה",
        "בצהריים",
    ]

    for text in messages:
        run_message(app, thread_id, text)


if __name__ == "__main__":
    main()
