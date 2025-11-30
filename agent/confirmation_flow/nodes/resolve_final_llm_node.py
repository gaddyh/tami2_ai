# nodes/resolve_final_llm_node.py
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Dict, Any

from openai import OpenAI, APIError, BadRequestError, APITimeoutError

from observability.obs import span_step, safe_update_current_span_io, mark_error
from agent.confirmation_flow.models import ConfirmationInitialResult

if TYPE_CHECKING:
    from agent.confirmation_flow.state import ConfirmationState

client = OpenAI(
    timeout=10,
    max_retries=1,
)

model = "gpt-4o"


def resolve_final_llm(state: "ConfirmationState") -> "ConfirmationState":
    """
    LLM #2:
    Input (in state):
      - query
      - options
      - user_answer
      - llm_messages (prepared by make_prepare_final_llm_node)

    Output:
      - state["final_result"] with shape:

        {
          "status": "done" | "cannot_resolve",
          "selected_item": dict | None
        }
    """
    with span_step("confirmation_final_llm_node", kind="node", node="confirmation_final_llm_node"):
        with span_step(
            "llm_call",
            kind="llm",
            as_type="generation",
            model=model,
            node="confirmation_final_llm_node",
        ) as _gen:
            messages = state.get("llm_messages") or []

            if not messages:
                # Developer bug: prepare_final_llm didn't run or didn't populate messages
                raise RuntimeError("resolve_final_llm: llm_messages is empty. Did prepare_final_llm run?")

            # log input
            safe_update_current_span_io(
                input={
                    "query": state.get("query"),
                    "options": state.get("options"),
                    "user_answer": state.get("user_answer"),
                    "messages": messages,
                },
                redact=True,
            )

            start = time.time()
            try:
                schema = ConfirmationInitialResult.model_json_schema()

                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "ConfirmationInitialResult",
                            "schema": schema,
                            # keep non-strict if you allow extra keys from the model
                            "strict": False,
                        },
                    },
                )

                elapsed = time.time() - start
                print(f"confirmation final LLM took {elapsed:.2f}s")
                print("LLM response (confirmation final):", resp)

                result_model = ConfirmationInitialResult.model_validate_json(
                    resp.choices[0].message.content
                )
                result_dict: Dict[str, Any] = result_model.model_dump()

                # log output
                safe_update_current_span_io(output=result_dict, redact=True)

                state["final_result"] = result_dict

            except (APITimeoutError, APIError, BadRequestError) as e:
                # Fallback: do not crash the graph, just mark cannot_resolve
                fallback: Dict[str, Any] = {
                    "status": "cannot_resolve",
                    "selected_item": None,
                }
                state["final_result"] = fallback
                mark_error(e, kind="LLMError", span=_gen)

            return state
