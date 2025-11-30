# nodes/entry_node.py
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.confirmation_flow.state import ConfirmationState


def confirmation_entry(state: "ConfirmationState") -> "ConfirmationState":
    """
    Optional init / normalization for the confirmation flow.
    """
    #print("\nConfirmation entry state:", state)
    state["initial_result"] = None
    state["final_result"] = None
    # You can choose to clear selected_item or keep it:
    # state["selected_item"] = None
    return state
