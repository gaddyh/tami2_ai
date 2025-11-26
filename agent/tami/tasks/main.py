# demo_notes_agent.py

from typing import Dict, Any
from agent.linear_flow.graph import build_agent_app
from agent.tami.tasks.tool_registery import tools_reference, tools
from agent.tami.tasks.prompt import TASKS_PLANNER_SYSTEM_PROMPT, TASKS_RESPONDER_SYSTEM_PROMPT
from observability.obs import instrument
from datetime import datetime
from typing import Optional
from models.agent_output import TamiOutput
from typing import Any

class Out(Any):
    trace_id: Optional[str] = None
# -------------------------------
# Build the app
# -------------------------------
from agent.tami.tasks.tool_registery import tools_reference, tools
system_prompt = TASKS_PLANNER_SYSTEM_PROMPT + "\n\n" + tools_reference

app = build_agent_app(
    project_name="tasks__linear_demo",
    planner_system_prompt=system_prompt,
    tools=tools,
    responder_system_prompt=TASKS_RESPONDER_SYSTEM_PROMPT,
)

def build_tasks_agent_graph():
    app = build_agent_app(
        project_name="tasks",
        planner_system_prompt=system_prompt,
        tools=tools,
        responder_system_prompt=TASKS_RESPONDER_SYSTEM_PROMPT,
    )
    return app
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



def main():
    print("Tasks Agent Demo. Type 'quit' to exit.\n")

    state: LinearAgentState = {
        "project": "tasks__linear_demo",
        "project_state": {
            "tasks": [],
        },
    }

    test_inputs1 = [
        "whats my tasks",
        "add 3 tasks:check mail, throw garbage, clean table",
        "whats my tasks",
        "delete 2",
        "whats my tasks",
    ]
    test_inputs2 = [
        """
        משימה
קרמיקות שבורות מתחת לארון חשמל בקומה 5 בבניין יצחק שמיר אחד (ראה בתמונה המצטרפת)
ליפקין שחק 2 , גבעת שמואל
        """,
    ]

    test_inputs = [
        "add 3 tasks:check mail, throw garbage, clean table",
        "whats my tasks",
        "i checked my mail already",
        "whats my tasks",
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
        result = run_agent_flow(state, config={"thread_id": "tasks__linear_demo" + testId})
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
