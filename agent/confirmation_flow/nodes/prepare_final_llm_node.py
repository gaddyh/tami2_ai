# agent/confirmation_flow/nodes/prepare_final_llm_node.py
from __future__ import annotations

import json
from typing import Callable, List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from agent.confirmation_flow.state import ConfirmationState


def make_prepare_final_llm_node(system_prompt: str) -> Callable[["ConfirmationState"], "ConfirmationState"]:
    """
    Factory for the node that prepares messages for the SECOND LLM.

    Here we have:
    - query
    - options
    - user_answer (after ask_user interrupt)

    Again, FW just structures data; prompt semantics are external.
    """

    def prepare_final_llm(state: "ConfirmationState") -> "ConfirmationState":
        query = state.get("query")
        options = state.get("options", [])
        user_answer = state.get("user_answer")

        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "query": query,
                        "options": options,
                        "user_answer": user_answer,
                    },
                    ensure_ascii=False,
                ),
            },
        ]

        state["llm_messages"] = messages
        return state

    return prepare_final_llm
