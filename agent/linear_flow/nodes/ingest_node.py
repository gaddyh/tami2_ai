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
    tz = ZoneInfo(tz_name)
    return dt.astimezone(tz)


def build_calendar_window(now: datetime, tz: ZoneInfo, days: int = 14):
    arr = []
    for i in range(days):
        d = now + timedelta(days=i)
        d = d.astimezone(tz)
        arr.append({
            "date": d.strftime("%Y-%m-%d"),
            "weekday": d.strftime("%a").upper()[0:2],  # SU MO TU ...
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
            ctx = state.get("context") or {}
            now = parse_context_datetime(ctx["current_datetime"], ctx["tz"])

            try:
                tz = ZoneInfo(ctx["tz"])
                ctx["calendar_window"] = build_calendar_window(now, tz, days=14)
            except Exception as e:
                print(f"Failed to build calendar window: {e}")
                raise

            # NOTE: we update state["context"] so later nodes see the enriched ctx
            state["context"] = ctx

            if ctx:
                messages.append(
                    {
                        "role": "system",
                        "content": "RUNTIME CONTEXT:\n```json\n"
                                   + json.dumps(ctx, ensure_ascii=False)
                                   + "\n```",
                    }
                )

            # ---- 2b) Person-resolution handling on numeric replies ----

            input_text = (state.get("input_text") or "").strip()
            needs_person_resolution = state.get("needs_person_resolution") is True
            person_resolution_items = state.get("person_resolution_items")

            # Only handle resolution attempts during an active resolution state
            if needs_person_resolution and isinstance(person_resolution_items, list):

                # Case A: User gave a non-digit → treat as "no resolution"
                if not input_text.isdigit():
                    # We DO NOT clear anything here.
                    # The planner/responder will simply ask again using the same candidates.
                    messages.append({
                        "role": "system",
                        "content": (
                            "INVALID PERSON SELECTION:\n"
                            f"user_input='{input_text}' (not a number)"
                        )
                    })
                    # continue to planner without resolving
                else:
                    idx_1based = int(input_text)
                    count = len(person_resolution_items)

                    # Case B: Out of range → ask again
                    if not (1 <= idx_1based <= count):
                        messages.append({
                            "role": "system",
                            "content": (
                                "INVALID PERSON SELECTION:\n"
                                f"user_input='{input_text}' index_out_of_range 1..{count}"
                            )
                        })
                        # Don't resolve anything; planner will ask again
                    else:
                        # Case C: Valid selection → resolve
                        chosen = person_resolution_items[idx_1based - 1]

                        # Put the chosen person into context
                        ctx.setdefault("resolved_person", chosen)
                        state["context"] = ctx

                        # Inform the planner about the resolved selection
                        messages.append(
                            {
                                "role": "system",
                                "content": (
                                    "RESOLVED PERSON SELECTION:\n```json\n"
                                    + json.dumps(
                                        {
                                            "user_selection_raw": input_text,
                                            "selected_index_1based": idx_1based,
                                            "selected_person": chosen,
                                        },
                                        ensure_ascii=False,
                                    )
                                    + "\n```"
                                ),
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
