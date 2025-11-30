# agent/confirmation_flow/nodes/prepare_initial_llm_node.py
from __future__ import annotations

import json
from typing import Callable, List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from agent.confirmation_flow.state import ConfirmationState


def make_prepare_initial_llm_node(system_prompt: str) -> Callable[["ConfirmationState"], "ConfirmationState"]:
    """
    Factory for the *framework* node that prepares messages for the FIRST LLM.

    The FW does not own the meaning of the prompt; it just:
    - receives a system_prompt from the caller
    - builds `state["initial_llm_messages"]` in a consistent shape
    """

    def prepare_initial_llm(state: "ConfirmationState") -> "ConfirmationState":
        query = state.get("query")
        options = state.get("options", [])

        # Caller is free to decide semantics, but FW gives a sane default:
        # system: instructions + schema (provided by caller)
        # user: minimal JSON payload with query + options
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
                    },
                    ensure_ascii=False,
                ),
            },
        ]

        state["llm_messages"] = messages
        #print("\nPrepare initial LLM state:", state)
        return state

    return prepare_initial_llm
