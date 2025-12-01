# agent/confirmation_flow/graph.py
from __future__ import annotations

from langgraph.graph import StateGraph, END
from agent.confirmation_flow.state import ConfirmationState

from agent.confirmation_flow.nodes.entry_node import confirmation_entry
from agent.confirmation_flow.nodes.prepare_initial_llm_node import make_prepare_initial_llm
from agent.confirmation_flow.nodes.resolve_initial_llm_node import resolve_initial_llm
from agent.confirmation_flow.nodes.ask_user_node import ask_user_node
from agent.confirmation_flow.nodes.prepare_final_llm_node import make_prepare_final_llm_node
from agent.confirmation_flow.nodes.resolve_final_llm_node import resolve_final_llm
from agent.confirmation_flow.nodes.apply_resolution_node import apply_resolution


# -------------------------------
# Routing logic
# -------------------------------

def route_from_initial(state: ConfirmationState) -> str:
    """
    Decide where to go after resolve_initial_llm based on initial_result["status"].
    - "ask_user"       -> ask_user
    - "done"           -> apply_resolution
    - "cannot_resolve" -> apply_resolution
    """
    initial = state.get("initial_result") or {}
    status = initial.get("status")

    if status == "ask_user":
        return "ask_user"

    # "done" or "cannot_resolve" both end in apply_resolution
    return "apply_resolution"


# -------------------------------
# Build app (FW)
# -------------------------------

def build_confirmation_flow_app(
    project_name: str,
    initial_system_prompt: str,
    final_system_prompt: str,
):
    """
    confirmation_flow FW:

      entry
        -> prepare_initial_llm      (injects initial_system_prompt)
        -> resolve_initial_llm      (LLM #1, schema: ConfirmationInitialResult)
        -> ask_user? or apply_resolution

      ask_user
        -> prepare_final_llm        (injects final_system_prompt, uses user_answer)
        -> resolve_final_llm        (LLM #2, final choice)
        -> apply_resolution
    """
    builder = StateGraph(ConfirmationState)

    # Nodes
    builder.add_node("entry", confirmation_entry)
    builder.add_node(
        "prepare_initial_llm",
        make_prepare_initial_llm(initial_system_prompt),
    )
    builder.add_node("resolve_initial_llm", resolve_initial_llm)
    builder.add_node("ask_user", ask_user_node)
    builder.add_node(
        "prepare_final_llm",
        make_prepare_final_llm_node(final_system_prompt),
    )
    builder.add_node("resolve_final_llm", resolve_final_llm)
    builder.add_node("apply_resolution", apply_resolution)

    # Entry
    builder.set_entry_point("entry")

    # entry → prepare_initial → initial LLM
    builder.add_edge("entry", "prepare_initial_llm")
    builder.add_edge("prepare_initial_llm", "resolve_initial_llm")

    # initial LLM → ask_user / apply_resolution
    builder.add_conditional_edges(
        "resolve_initial_llm",
        route_from_initial,
        {
            "ask_user": "ask_user",
            "apply_resolution": "apply_resolution",
        },
    )

    # ask_user → prepare_final → final LLM → apply_resolution
    builder.add_edge("ask_user", "prepare_final_llm")
    builder.add_edge("prepare_final_llm", "resolve_final_llm")
    builder.add_edge("resolve_final_llm", "apply_resolution")

    # apply_resolution → END
    builder.add_edge("apply_resolution", END)

    return builder
