from agent.linear_flow.state import LinearAgentState
from langgraph.types import interrupt
from agent.linear_flow.utils import add_message

def handle_followup(state: LinearAgentState) -> LinearAgentState:
    question = state.get("followup_message") or ""

    payload = {
        "type": "followup",
        "question": question,
        "agent": state.get("target_agent"),   # if you track this
        "meta": {
            "project": state.get("project"),
        },
    }

    # This will PAUSE the graph and bubble up to your app
    answer = interrupt(payload)
    if isinstance(answer, dict):
        content = answer.get("content", "")
    else:
        content = str(answer)

    add_message("user", content, state)
    add_message("user", content, state, "llm_messages")
    # When resumed, answer is the user's reply
    state["followup_message"] = None
    return state
