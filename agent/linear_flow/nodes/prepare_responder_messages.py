# linear_flow/nodes/prepare_responder_messages.py
import json
from typing import Callable, Dict, Any
from agent.linear_flow.state import LinearAgentState
from observability.obs import span_step, safe_update_current_span_io

def make_prepare_responder_messages_node(
    responder_system_prompt: str,
) -> Callable[[LinearAgentState], LinearAgentState]:
    """
    Build llm_messages for the responder LLM:
    - responder-specific system prompt
    - context + tool_results as JSON
    - chat history (messages)
    """

    def prepare_responder_messages(state: LinearAgentState) -> LinearAgentState:
        with span_step(
            "prepare_responder_messages",
            kind="node",
            node="prepare_responder_messages",
        ):
            context: Dict[str, Any] = state.get("context") or {}
            tool_results = state.get("tool_results", [])
            history = state.get("messages") or []

            messages = []

            # 1) System prompt for responder
            messages.append(
                {
                    "role": "system",
                    "content": (
                        responder_system_prompt
                        + "\n\n"
                        "You are the *responder* model. "
                        "Write a SHORT, clear reply in Hebrew for the user. "
                        "Do not mention tools, JSON, or internal IDs."
                    ),
                }
            )

            # 2) Context + tool_results as a single system message
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "RUNTIME CONTEXT WITH TOOL RESULTS:\n```json\n"
                        + json.dumps(
                            {
                                "context": context,
                                "tool_results": tool_results,
                            },
                            ensure_ascii=False,
                        )
                        + "\n```"
                    ),
                }
            )

            # 3) Chat history (user/assistant)
            messages.extend(history)

            state["llm_messages"] = messages
            safe_update_current_span_io(
                input={"context": context, "messages": messages},
                redact=True,
            )
            return state

    return prepare_responder_messages
