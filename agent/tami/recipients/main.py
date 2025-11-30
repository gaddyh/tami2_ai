# agent/recipients_agent/graph.py
from __future__ import annotations

from langgraph.graph import StateGraph
from agent.confirmation_flow.graph import build_confirmation_flow_app
from agent.tami.recipients.prompt import RECIPIENTS_INITIAL_SYSTEM_PROMPT, RECIPIENTS_FINAL_SYSTEM_PROMPT

def build_recipients_agent_app() -> StateGraph:
    """
    Build a concrete recipients agent on top of confirmation_flow FW.

    - initial_system_prompt: your existing prompt for deciding:
        "done" / "ask_user" / "cannot_resolve"
    - final_system_prompt: prompt for using user_answer to pick exactly one candidate.

    State expectations (before invoking the graph):

      state["query"]   = name to resolve        (e.g. raw_query / "גל")
      state["options"] = list of candidates     (from your _mk_candidate)

    Result:

      state["selected_item"] = the chosen candidate dict OR None
    """
    app = build_confirmation_flow_app(
        project_name="recipients_agent",
        initial_system_prompt=RECIPIENTS_INITIAL_SYSTEM_PROMPT,
        final_system_prompt=RECIPIENTS_FINAL_SYSTEM_PROMPT,
    )
    return app


recipients_app = build_recipients_agent_app()

from agent.confirmation_flow.runner import handle_confirmation_turn
from agent.confirmation_flow.state import ConfirmationState

# When you have search result:
# { "name": raw_query, "candidates": [cand...], "count": ..., "ts": ... }
def run_recipients_agent(thread_id: str, search_result):
    state: ConfirmationState = {
        "query": search_result["name"],
        "options": search_result["candidates"],
    }
    # config/thread_id as usual for LangGraph
    out_state = handle_confirmation_turn(recipients_app, thread_id, None, state)
    return out_state.get("selected_item")
