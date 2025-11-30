# nodes/apply_resolution_node.py
from __future__ import annotations
from typing import TYPE_CHECKING, Dict, Any, Optional

if TYPE_CHECKING:
    from agent.confirmation_flow.state import ConfirmationState


def apply_resolution(state: "ConfirmationState") -> "ConfirmationState":
    """
    Final node.
    - Decide selected_item from initial_result/final_result.
    - Do NOT perform DB side-effects here; this graph stays pure.
      The caller can read state["selected_item"] and act.
    """
    selected: Optional[Dict[str, Any]] = None

    initial = state.get("initial_result") or {}
    final = state.get("final_result") or {}

    if final.get("selected_item") is not None:
        selected = final["selected_item"]
    elif initial.get("selected_item") is not None:
        selected = initial["selected_item"]

    state["selected_item"] = selected
    return state
