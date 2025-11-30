
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

    Usage pattern:

    - First call:
        handle_confirmation_turn(app, thread_id, user_message=None, base_state=initial_state)

      (initial_state should contain: query, options, etc.)

    - If status == "interrupt":
        - read interrupt.value["question"], send to user
        - later, when user replies → call again with same thread_id and user_message=<reply>

    - On resume calls:
        handle_confirmation_turn(app, thread_id, user_message=<user_reply>)
    """
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = app.get_state(config)

    # Pending interrupts from a previous run?
    interrupts: tuple[Any, ...] = ()
    if snapshot is not None:
        interrupts = getattr(snapshot, "interrupts", ()) or ()

    # 1) We are in the middle of a clarification → RESUME
    if interrupts:
        intr = interrupts[0]
        # For confirmation_flow we treat user_message as the raw answer
        print("\nUser reply:", user_message)
        resume_value = {"content": "" if user_message is None else str(user_message)}
        result = app.invoke(Command(resume=resume_value), config=config)

    else:
        # 2) Fresh run → start with base_state only
        #print("\nBase state:", base_state)
        state: Dict[str, Any] = dict(base_state or {})
        result = app.invoke(state, config=config)

    # -------------------------------------------------
    # Normalize return: interrupt vs plain state
    # -------------------------------------------------
    if isinstance(result, dict) and result.get("__interrupt__"):
        # Get the latest interrupts from checkpoint
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

    # Plain state
    return {
        "status": "ok",
        "interrupt": None,
        "interrupts": None,
        "state": result,
    }