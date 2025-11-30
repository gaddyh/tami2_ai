# nodes/ask_user_node.py
from __future__ import annotations

from typing import TYPE_CHECKING
from langgraph.types import interrupt

if TYPE_CHECKING:
    from agent.confirmation_flow.state import ConfirmationState


def ask_user_node(state: "ConfirmationState") -> "ConfirmationState":
    """
    Interrupt node (no LLM here).

    - Reads state["initial_result"]["question"].
    - Calls interrupt(...) -> graph pauses and returns an Interrupt.
    - On resume, interrupt(...) returns the user's reply.
    - Stores reply in state["user_answer"].
    """
    initial = state.get("initial_result") or {}
    question = initial.get("question") or ""

    user_reply = interrupt(
        {
            "type": "confirmation_question",
            "question": question,
            "query": state.get("query"),
            "options": state.get("options", []),
        }
    )

    # When resumed, execution continues here:
    state["user_answer"] = str(user_reply)
    return state
