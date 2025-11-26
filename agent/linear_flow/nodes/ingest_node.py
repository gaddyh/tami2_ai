from agent.linear_flow.state import LinearAgentState
import json
from typing import List, Dict, Any, Callable
from observability.obs import span_step, safe_update_current_span_io

MAX_HISTORY = 10  # or whatever

def make_ingest_node(system_prompt: str) -> Callable[[LinearAgentState], LinearAgentState]:
    def ingest(state: LinearAgentState) -> LinearAgentState:
        with span_step("ingest", kind="node", node="ingest"):
            messages: List[Dict[str, Any]] = []

            # 1) System prompt
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})

            # 2) Context as system message
            ctx = state.get("context")
            if ctx:
                messages.append(
                    {
                        "role": "system",
                        "content": "RUNTIME CONTEXT:\n```json\n"
                                   + json.dumps(ctx, ensure_ascii=False)
                                   + "\n```",
                    }
                )

            # 3) Past chat messages (user/assistant) – trim BEFORE using
            history: List[Dict[str, Any]] = state.get("messages") or []
            trimmed_history = history[-MAX_HISTORY:]
            state["messages"] = trimmed_history  # if you really want to mutate state
            messages.extend(trimmed_history)

            # 4) Current user input
            input_text = state.get("input_text") or ""
            if input_text:
                user_msg = {"role": "user", "content": input_text}
                messages.append(user_msg)
                state.setdefault("messages", []).append(user_msg)

            state["llm_messages"] = messages
            safe_update_current_span_io(input=messages, redact=True)
            return state

    return ingest
