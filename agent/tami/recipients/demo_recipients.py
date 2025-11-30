# agent/recipients_agent/demo_recipients.py
from __future__ import annotations

from pprint import pprint

from agent.confirmation_flow.state import ConfirmationState
from agent.tami.recipients.main import recipients_app
from agent.confirmation_flow.runner import handle_confirmation_turn
from langgraph.checkpoint.memory import MemorySaver


def run_recipients_agent_example() -> None:
    # recipients_app might be:
    # - a StateGraph (builder), OR
    # - an already compiled app (has get_state/invoke)
    app = recipients_app

    # If it's not compiled yet, compile with an in-memory checkpointer
    if not hasattr(app, "get_state"):
        checkpointer = MemorySaver()
        app = app.compile(checkpointer=checkpointer)

    thread_id = "recipients-demo-1"

    # 1) Example input from your search:
    search_result = {
        "name": "גל",
        "candidates": [
            {
                "display_name": "גל ליס",
                "score": 0.92,
                "type": "person",
                "chat_id": "9725...@c.us",
                "phone": "+9725...",
                "email": "gal.lis@example.com",
            },
            {
                "display_name": "גל כהן",
                "score": 0.89,
                "type": "person",
                "chat_id": "9725...@c.us",
                "phone": "+9725...",
                "email": "gal.cohen@example.com",
            },
        ],
    }

    # 2) Initial confirmation state for the graph
    base_state: ConfirmationState = {
        "query": search_result["name"],
        "options": search_result["candidates"],
    }

    # 3) First run: start the confirmation_flow
    print("=== RUN 1: initial confirmation_flow run ===")
    result1 = handle_confirmation_turn(
        app=app,
        thread_id=thread_id,
        user_message=None,       # no user reply yet
        base_state=base_state,
    )

    if result1["status"] == "interrupt":
        intr = result1["interrupt"]
        print("\n=== INTERRUPT RECEIVED ===")
        pprint(intr)

        # In real life you would send intr.value["question"] to WhatsApp.
        # For the demo we just print it and simulate a reply.
        try:
            question = intr.value.get("question")  # type: ignore[attr-defined]
        except AttributeError:
            # depending on your Interrupt type, adjust this accessor
            question = None

        print("\nQuestion to user:")
        print(question or "<no question field>")

        # Simulate user reply:
        simulated_user_reply = "1"
        print("\nSimulated user reply:", simulated_user_reply)

        # 4) Second run: resume with the user's answer
        print("\n=== RUN 2: resume with user_answer ===")
        result2 = handle_confirmation_turn(
            app=app,
            thread_id=thread_id,
            user_message=simulated_user_reply,
            base_state=None,      # ignored on resume
        )

        if result2["status"] != "ok":
            print("\nUnexpected status on second run:", result2["status"])
            return

        final_state = result2["state"] or {}
    else:
        # No interrupt: confirmation finished in one shot
        final_state = result1["state"] or {}

    # 5) Show result
    print("\n=== FINAL CONFIRMATION STATE ===")
    pprint(final_state)
    print("\n=== SELECTED ITEM ===")
    pprint(final_state.get("selected_item"))


if __name__ == "__main__":
    run_recipients_agent_example()
