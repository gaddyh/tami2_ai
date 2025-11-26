from agent.linear_flow.state import LinearAgentState
import json
from typing import List, Dict, Any, Callable
from observability.obs import span_step, safe_update_current_span_io
from agent.linear_flow.utils import add_message

MAX_HISTORY = 10  # per agent

def make_ingest_node(system_prompt: str) -> Callable[[LinearAgentState], LinearAgentState]:
    def ingest(state: LinearAgentState) -> LinearAgentState:
        with span_step("ingest", kind="node", node="ingest"):
            target_agent = state.get("target_agent")
            if not target_agent:
                raise ValueError("ingest: state['target_agent'] must be set before ingest")

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

            # 3) Past chat messages for THIS target_agent only
            all_history: List[Dict[str, Any]] = state.get("messages") or []
            per_agent_history = [
                m
                for m in all_history
                if m.get("target_agent") == target_agent
                and m.get("role") in ("user", "assistant")
            ]

            trimmed_history = per_agent_history[-MAX_HISTORY:]
            messages.extend(trimmed_history)

            # 4) Current user input – must go into BOTH llm_messages and state["messages"]
            input_text = state.get("input_text") or ""
            if input_text:
                # What planner sees now:
                messages.append({"role": "user", "content": input_text})
                # Persistent tagged history:
                add_message("user", input_text, state)

            state["llm_messages"] = messages
            safe_update_current_span_io(
                input={"context": ctx, "messages": messages},
                redact=True,
            )
            return state

    return ingest
