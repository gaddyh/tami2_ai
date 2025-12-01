from typing import Dict, Any, List
import json

from agent.confirmation_flow.state import ConfirmationState

def make_prepare_initial_llm(system_prompt: str):
    def prepare_initial_llm(state: "ConfirmationState") -> "ConfirmationState":
        """
        Build the FIRST LLM call for the persons / confirmation agent.

        Inputs it expects on state (coming from Tami postprocess):
        - context: the runtime context dict (with .text, etc.)
        - person_resolution_items: list[dict] with one or more resolution items:
            {
                "source_tool": "process_event",
                "mode": "create",
                "entity_type": "event",
                "entity_id": "event_7a157804" | None,
                "tool_args": {...},    # original tool args
                "participants": [ {"name": "...", "email": ""}, ... ]
            }

        It will:
        - pick the first resolution item
        - stash it as state["resolution_item"]
        - build fresh llm_messages for the confirmation LLM.
        """
        from typing import Any, Dict, List
        import json

        # 1) Pull context and resolution items from shared state
        ctx: Dict[str, Any] = state.get("context", {}) or {}
        resolution_items: List[Dict[str, Any]] = state.get("person_resolution_items") or []
        if not resolution_items:
            raise ValueError("prepare_initial_llm: missing person_resolution_items in state")

        resolution_item = resolution_items[0]
        participants = (
            resolution_item.get("participants")
            or resolution_item.get("tool_args", {}).get("participants")
            or []
        )

        # 2) Build minimal payload for the LLM
        original_text = ctx.get("text")
        payload: Dict[str, Any] = {
            "original_text": original_text,
            "mode": resolution_item.get("mode"),
            "entity_type": resolution_item.get("entity_type"),
            "entity_id": resolution_item.get("entity_id"),
            "participants": participants,
            # Optional: if you want the model to see raw tool args:
            "tool_args": resolution_item.get("tool_args"),
        }

        # 3) Store current resolution item on state for later nodes
        state["resolution_item"] = resolution_item

        # 4) **CRITICAL**: overwrite llm_messages (do NOT append to old responder messages)
        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": system_prompt,  # your persons / confirmation system prompt
            },
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False),
            },
        ]

        state["llm_messages"] = messages
        return state


    return prepare_initial_llm
