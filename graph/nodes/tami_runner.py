# agent/tami_runner.py
from typing import Optional, List, Dict, Any

from graph.app import tami_graph_app
from graph.state import TamiState
from agent.sessions import get_session
from models.input import In
from models.agent_output import TamiOutput
from graph.history import convert_session_to_messages


async def _build_context(in_: In) -> dict:
    return {
        "user_id": in_.user_id,
        "tz": in_.tz,
        "source": in_.source,
        "locale": in_.locale,
    }


async def _load_history_messages(session, max_items: int = 40) -> List[Dict[str, Any]]:
    """
    Load recent session items and convert them to chat messages
    usable by the LLM.

    We rely on convert_session_to_messages to strip tools/metadata.
    """
    raw_items = await session.get_items(limit=max_items)
    history_messages = convert_session_to_messages(raw_items)
    return history_messages


async def run_tami_turn(in_: In) -> TamiOutput:
    session = get_session(in_.user_id, in_.thread_id)
    context = await _build_context(in_)

    # NEW: load history from your SQLite session
    history_messages = await _load_history_messages(session, max_items=40)

    state: TamiState = {
        "input_text": in_.text or "",
        "context": context,
        "history": history_messages,
    }

    final_state: TamiState = await tami_graph_app.ainvoke(state)
    reply_text: str = final_state.get("final_output", "") or ""

    # Persist only user + assistant messages
    await session.add_items(
        [
            {
                "role": "user",
                "content": in_.text or "",
            },
            {
                "role": "assistant",
                "content": reply_text,
            },
        ]
    )

    return TamiOutput(
        final_output=reply_text,
        trace_id=None,
    )
