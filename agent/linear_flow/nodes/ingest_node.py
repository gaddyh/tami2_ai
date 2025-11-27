from agent.linear_flow.state import LinearAgentState
import json
from typing import List, Dict, Any, Callable
from observability.obs import span_step, safe_update_current_span_io
from agent.linear_flow.utils import add_message

MAX_HISTORY = 10  # per agent


from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

def parse_context_datetime(dt_str: str, tz_name: str) -> datetime:
    # dt_str already contains the offset, so this is safe:
    dt = datetime.fromisoformat(dt_str)

    # ensure timezone of tz_name
    # (in most cases dt already has +02:00, so this just checks consistency)
    tz = ZoneInfo(tz_name)
    return dt.astimezone(tz)

def build_calendar_window(now: datetime, tz: ZoneInfo, days: int = 14):
    arr = []
    for i in range(days):
        d = now + timedelta(days=i)
        d = d.astimezone(tz)
        arr.append({
            "date": d.strftime("%Y-%m-%d"),
            "weekday": d.strftime("%a").upper()[0:2]  # SU MO TU ...
        })
    return arr

def make_ingest_node(system_prompt: str) -> Callable[[LinearAgentState], LinearAgentState]:
    def ingest(state: LinearAgentState) -> LinearAgentState:
        with span_step("ingest", kind="node", node="ingest"):
            target_agent = state.get("target_agent")
            if not target_agent:
                raise ValueError("ingest: state['target_agent'] must be set before ingest")

            messages: List[Dict[str, Any]] = []
            print(f"ingest: current_datetime={state.get('context', {}).get('current_datetime', '')}")
            # 1) System prompt
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})

            # 2) Context as system message
            ctx = state.get("context")
            now = parse_context_datetime(ctx["current_datetime"], ctx["tz"])

            try:
                tz = ZoneInfo(ctx["tz"])
                ctx["calendar_window"] = build_calendar_window(now, tz, days=14)
            except Exception as e:
                print(f"Failed to build calendar window: {e}")
                raise
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
