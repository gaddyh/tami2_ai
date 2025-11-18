# agent/tami_runner.py
from typing import Optional, List, Dict, Any

from graph.app import tami_graph_app
from graph.state import TamiState
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
    context = await _build_context(in_)

    state: TamiState = {
        "input_text": in_.text or "",
        "context": context,
    }

    config = {
        "configurable": {
            # REQUIRED for checkpointer:
            "thread_id": in_.thread_id or in_.user_id or "cli-test",
            # optional, but useful for routing/analytics:
            "user_id": in_.user_id,
            # optional namespace if you want to separate chat/scheduler/etc. later
            # "checkpoint_ns": "chat",
        }
    }

    final_state: TamiState = tami_graph_app.invoke(state, config=config)
    reply_text: str = final_state.get("final_output", "") or ""

    return TamiOutput(
        final_output=reply_text,
        trace_id=None,
    )
