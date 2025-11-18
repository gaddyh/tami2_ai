# graph/app.py (for example)

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

from graph.nodes.prepare_messages import prepare_messages_node
from graph.nodes.tami_llm import tami_llm_node
from graph.nodes.call_tools import call_tools_node
from graph.state import TamiState

# Create ONE saver for the whole process
checkpointer = SqliteSaver.from_file("tami_graph.db")


def debug_log_node(state: TamiState) -> TamiState:
    # print("[debug_log_node] messages:", state.get("messages"))
    # print("[debug_log_node] final_output:", state.get("final_output"))
    return state


def should_call_tools(state: TamiState) -> str:
    """
    Decide whether to go to call_tools or finish.
    """
    messages = state.get("messages", [])
    if not messages:
        return "end"

    last_msg = messages[-1]
    tool_calls = last_msg.get("tool_calls", [])

    if tool_calls:
        return "call_tools"

    return "end"


def build_tami_app():
    """
    Minimal LangGraph app for Tami:

        START
          → prepare_messages
          → tami_llm
             ├─(tool_calls)→ call_tools → tami_llm → ... (second step)
             └─(no tools) → debug_log → END
    """
    graph = StateGraph(TamiState)

    graph.add_node("prepare_messages", prepare_messages_node)
    graph.add_node("tami_llm", tami_llm_node)
    graph.add_node("call_tools", call_tools_node)
    graph.add_node("debug_log", debug_log_node)

    graph.set_entry_point("prepare_messages")
    graph.add_edge("prepare_messages", "tami_llm")

    graph.add_conditional_edges(
        "tami_llm",
        should_call_tools,
        {
            "call_tools": "call_tools",
            "end": "debug_log",
        },
    )

    graph.add_edge("call_tools", "tami_llm")
    graph.add_edge("debug_log", END)

    # ⬅️ key line: make the graph stateful
    app = graph.compile(checkpointer=checkpointer)
    return app
