from typing import Any, Dict, List
from agent.linear_flow.state import LinearAgentState


def _is_unresolved_person(p: Dict[str, Any]) -> bool:
    """
    Treat as unresolved if we only have a name and no strong identifier.
    In your log, email=None is exactly this case.
    """
    if not isinstance(p, dict):
        return False

    name = (p.get("name") or "").strip()
    if not name:
        return False

    # If we already have any strong identifier, it's resolved enough
    if p.get("contact_id"):
        return False
    if p.get("email"):
        return False
    if p.get("phone"):
        return False

    # name-only → unresolved
    return True


def postprocess_node(state: LinearAgentState) -> LinearAgentState:
    context: Dict[str, Any] = state.get("context") or {}
    tools_ctx: Dict[str, Any] = context.get("tools") or {}

    resolution_items: List[Dict[str, Any]] = []

    # ---- handle process_event specifically ----
    pe = tools_ctx.get("process_event") or {}

    # Prefer a *successful* latest; if none, fall back to last_error
    record = pe.get("latest") or pe.get("last_error")

    if record:
        args = record.get("args") or {}
        result = record.get("result") or {}

        participants = None
        entity_id = None
        mode = "update"  # assume we’re updating an existing event if we have a result

        # 1) Success case: result contains the created/updated event
        if isinstance(result, dict) and "event" in result:
            event = result["event"]
            participants = (
                event.get("participants")
                or event.get("attendees")
            )
            entity_id = event.get("id") or event.get("event_id")
            mode = "update"

        # 2) Error case like your log: result=None, but args has participants
        if not participants and isinstance(args, dict):
            participants = args.get("participants")
            entity_id = None
            mode = "create"  # we never actually created the event

        unresolved = [
            p for p in (participants or []) if _is_unresolved_person(p)
        ]

        if unresolved:
            resolution_items.append(
                {
                    "source_tool": "process_event",
                    "mode": mode,           # "create" or "update"
                    "entity_type": "event",
                    "entity_id": entity_id, # None in your current log
                    "tool_args": args,      # full args so recipients_agent can retry
                    "participants": unresolved,
                }
            )

    # ---- (later you can add process_comms here in the same style) ----

    if resolution_items:
        state["person_resolution_items"] = resolution_items
        state["needs_person_resolution"] = True
    else:
        state["person_resolution_items"] = []
        state["needs_person_resolution"] = False

    state["context"] = context
    print("postprocess_node", state)
    return state
