from langgraph.graph import StateGraph, END
from agent.linear_flow.state import LinearAgentState
from agent.linear_flow.tools import ToolRegistry
from agent.linear_flow.nodes.ingest_node import make_ingest_node
from agent.linear_flow.nodes.planner_llm_node import planner_llm
from agent.linear_flow.nodes.execute_tools_node import make_execute_tools_node
from agent.linear_flow.nodes.prepare_responder_messages import make_prepare_responder_messages_node
from agent.linear_flow.nodes.responder_llm_node import responder_llm
from agent.linear_flow.nodes.handle_planner_followup_node import handle_planner_followup
from langgraph.checkpoint.memory import MemorySaver

# -------------------------------
# Routing logic
# -------------------------------
def route_from_planner(state: LinearAgentState) -> str:
    if state.get("followup_message"):
        return "handle_planner_followup"

    if state.get("actions"):
        return "execute_tools"

    # no followup, no actions → go to prepare_responder_messages
    return "prepare_responder_messages"

# -------------------------------
# Build the graph
# -------------------------------
def build_agent_app(
    project_name: str,
    planner_system_prompt: str,  # must include tools schema
    tools: ToolRegistry,
    responder_system_prompt: str,
) -> StateGraph:
    builder = StateGraph(LinearAgentState)

    # Nodes
    builder.add_node("ingest", make_ingest_node(planner_system_prompt))
    builder.add_node("planner_llm", planner_llm)
    builder.add_node("execute_tools", make_execute_tools_node(tools))
    builder.add_node(
        "prepare_responder_messages",
        make_prepare_responder_messages_node(responder_system_prompt),
    )
    builder.add_node("responder_llm", responder_llm)
    builder.add_node("handle_planner_followup", handle_planner_followup)

    # Entry
    builder.set_entry_point("ingest")

    # ingest → planner
    builder.add_edge("ingest", "planner_llm")

    # Conditional edges out of planner
    builder.add_conditional_edges(
        "planner_llm",
        route_from_planner,
        {
            "handle_planner_followup": "handle_planner_followup",
            "execute_tools": "execute_tools",
            "prepare_responder_messages": "prepare_responder_messages",
        },
    )

    # planner followup loop
    builder.add_edge("handle_planner_followup", "planner_llm")

    builder.add_edge("execute_tools", "prepare_responder_messages")
    builder.add_edge("prepare_responder_messages", "responder_llm")
    builder.add_edge("responder_llm", END)
    
    app = builder.compile()
    return app