# graph/build.py

import sqlite3
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

from graph.state import TamiState
from graph.nodes.prepare_messages import prepare_messages_node
from graph.nodes.tami_llm import tami_llm_node
from graph.nodes.call_tools import call_tools_node


def debug_log_node(state: TamiState) -> TamiState:
    return state


def should_call_tools(state: TamiState) -> str:
    messages = state.get("messages", [])
    if not messages:
        return "end"
    last_msg = messages[-1]
    tool_calls = last_msg.get("tool_calls", [])
    return "call_tools" if tool_calls else "end"


def build_tami_app():
    # Create a real sqlite3 connection, not a path string
    conn = sqlite3.connect("tami_graph.db", check_same_thread=False)
    checkpointer = SqliteSaver(conn)

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

    return graph.compile(checkpointer=checkpointer)
