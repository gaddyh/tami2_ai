from agent.linear_flow.state import LinearAgentState
from langgraph.types import interrupt

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

    state.setdefault("messages", []).append(
                    {"role": "user", "content": content}
                )
    state.setdefault("llm_messages", []).append(
                    {"role": "user", "content": content}
                )
    # When resumed, answer is the user's reply
    state["followup_message"] = None
    return state
