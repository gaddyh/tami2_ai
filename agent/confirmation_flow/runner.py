
from typing import Any, Dict, Optional
from langgraph.types import Command

from typing import Any, Dict, Optional
from langgraph.types import Command

def handle_confirmation_turn(
    app,
    thread_id: str,
    user_message: Any | None,
    base_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generic interrupt-aware runner for confirmation_flow / recipients_agent.

    Returns:
        {
          "status": "interrupt" | "ok",
          "interrupt": Interrupt | None,
          "interrupts": tuple[Interrupt, ...] | None,
          "state": dict | None,
        }
    """
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = app.get_state(config)

    interrupts: tuple[Any, ...] = ()
    if snapshot is not None:
        interrupts = getattr(snapshot, "interrupts", ()) or ()

    # 1) We are in the middle of a clarification → RESUME
    if interrupts:
        print("\nUser reply:", user_message)
        # pass raw string back into the interrupt
        resume_value = "" if user_message is None else str(user_message)
        result = app.invoke(Command(resume=resume_value), config=config)

    else:
        # 2) Fresh run → start with base_state only (query + options)
        state: Dict[str, Any] = dict(base_state or {})
        result = app.invoke(state, config=config)

    # -------------------------------------------------
    # Normalize return: interrupt vs plain state
    # -------------------------------------------------
    if isinstance(result, dict) and result.get("__interrupt__"):
        snapshot = app.get_state(config)
        interrupts = ()
        if snapshot is not None:
            interrupts = getattr(snapshot, "interrupts", ()) or ()
        intr = interrupts[0] if interrupts else None

        return {
            "status": "interrupt",
            "interrupt": intr,
            "interrupts": interrupts,
            "state": None,
        }

    return {
        "status": "ok",
        "interrupt": None,
        "interrupts": None,
        "state": result,
    }
