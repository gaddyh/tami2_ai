# tami/graph.py

from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from agent.linear_flow.state import LinearAgentState

from agent.tami.tasks.main import build_tasks_agent_graph
from agent.tami.events.main import build_events_agent_graph
from agent.tami.comms.main import build_comms_agent_graph
from agent.tami.router_graph import route_node
from langgraph.types import Command, Interrupt

def postprocess_node(state: LinearAgentState) -> LinearAgentState:
    # eventually: normalize / choose response field
    #print(f"postprocess_node: {state}")
    return state

from typing import Optional, Dict, Any

def handle_tami_turn(
    app,
    thread_id: str,
    user_message: Any,
    base_state: Optional[Dict[str, Any]] = None,
):
    """
    base_state: whatever you currently pass as `state` on a fresh turn
                (e.g. {"project": "tami", "context": {...}}).
    """

    config = {"configurable": {"thread_id": thread_id}}
    snapshot = app.get_state(config)

    interrupts: tuple[Interrupt, ...] = ()
    if snapshot is not None:
        interrupts = getattr(snapshot, "interrupts", ()) or ()

    # 1) We are in the middle of a followup -> RESUME
    if interrupts:
        intr = interrupts[0]
        # Optional: assert it's our followup interrupt
        # if intr.value.get("type") != "followup": ...

        # Match your `handle_followup` contract: answer is a dict with "content"
        resume_value = {"content": str(user_message)}
        return app.invoke(Command(resume=resume_value), config=config)

    # 2) Fresh turn -> start with full state object
    state: Dict[str, Any] = dict(base_state or {})
    # whatever your graph expects as input
    state["input_text"] = str(user_message)

    # If you also want to seed messages/llm_messages here, you can:
    # state.setdefault("messages", []).append({"role": "user", "content": state["input_text"]})
    # state.setdefault("llm_messages", []).append({"role": "user", "content": state["input_text"]})

    return app.invoke(state, config=config)

def build_tami_router_app():
    # Get uncompiled graphs
    tasks_graph = build_tasks_agent_graph()
    events_graph = build_events_agent_graph()
    comms_graph = build_comms_agent_graph()
    #info_graph = build_info_agent_graph()

    builder = StateGraph(LinearAgentState)

    # 1. Router + postprocess
    builder.add_node("route", route_node)
    builder.add_node("postprocess", postprocess_node)

    # 2. Subgraphs as nodes (uncompiled graphs)
    builder.add_node("tasks_agent", tasks_graph)
    builder.add_node("events_agent", events_graph)
    builder.add_node("comms_agent", comms_graph)
    #builder.add_node("info_agent", info_graph)

    # 3. Entry
    builder.set_entry_point("route")

    # 4. Conditional routing
    def choose_agent(state: LinearAgentState) -> str:
        return state.get("target_agent", "tasks")

    builder.add_conditional_edges(
        "route",
        choose_agent,
        {
            "tasks": "tasks_agent",
            "events": "events_agent",
            "comms": "comms_agent",
            #"info": "info_agent",
        },
    )

    # 5. After any subgraph → postprocess → END
    builder.add_edge("tasks_agent", "postprocess")
    builder.add_edge("events_agent", "postprocess")
    builder.add_edge("comms_agent", "postprocess")
    builder.add_edge("postprocess", END)

    # 6. Single shared checkpointer for the whole system
    checkpointer = MemorySaver()
    app = builder.compile(checkpointer=checkpointer)
    return app
