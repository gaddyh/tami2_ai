# demo_notes_agent.py

from typing import Dict, Any
from agent.linear_flow.graph import build_agent_app
from agent.tami.events.tool_registery import tools_reference, tools
from agent.tami.events.prompt import EVENTS_PLANNER_SYSTEM_PROMPT, EVENTS_RESPONDER_SYSTEM_PROMPT
from observability.obs import instrument
from datetime import datetime
from models.input import In
from typing import Optional
from models.agent_output import TamiOutput
from typing import Any

class Out(Any):
    trace_id: Optional[str] = None
# -------------------------------
# Build the app
# -------------------------------
system_prompt = EVENTS_PLANNER_SYSTEM_PROMPT + "\n\n" + tools_reference

def build_events_agent_graph():
    app = build_agent_app(
        project_name="events",
        planner_system_prompt=system_prompt,
        tools=tools,
        responder_system_prompt=EVENTS_RESPONDER_SYSTEM_PROMPT,
    )
    return app

app = build_events_agent_graph()
# -------------------------------
# Tiny CLI loop to test
# -------------------------------

from agent.linear_flow.state import LinearAgentState
from observability.obs import instrument
import time
import uuid
@instrument(agent="tasks_linear_agent", operation="run", schema_version="tasks.v1")
def run_agent_flow(state: LinearAgentState, config: Dict[str, Any]) -> LinearAgentState:
    result = app.invoke(state, config=config)
    return result


def _now_iso() -> str:
    return datetime.now().isoformat()

async def process_input(inp: In) -> Out | TamiOutput:
    with set_common_trace_attrs(inp, extra_metadata={"agent.root": "input"}):
        with span_step("route.route_input", kind="RouteError", operation="route") as s:
            safe_update_current_span_io(input=inp)  # optional (keeps block-local IO too)



def main():
    print("Events Agent Demo. Type 'quit' to exit.\n")

    state: LinearAgentState = {
        "project": "events",
        "project_state": {
            "events": [],
        },
    }

    test_inputs = [
        "whats my events",
        "add event:shopping tomorrow at 14",
        "whats my events",
    ]
    testId = uuid.uuid4().hex
    for user in test_inputs:
        print("You:", user)
        state: LinearAgentState = {
            "input_text": user,
            "context": {
                "current_datetime": _now_iso(),
                "default_tz": "Asia/Jerusalem",
            },
        }
        
        start = time.perf_counter_ns()
        result = run_agent_flow(state, config={"thread_id": "events" + testId})
        state = result
        elapsed = (time.perf_counter_ns() - start) / 1e6
        print(f"Agent flow took {elapsed:.2f}ms")

        reply = (
            state.get("final_message")
            or state.get("followup_message")
            or state.get("response")
            or "(no reply)"
        )
        print("\nBot:", reply)




if __name__ == "__main__":
    main()
