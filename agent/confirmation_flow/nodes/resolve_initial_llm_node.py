# agent/confirmation_flow/nodes/resolve_initial_llm_node.py
from __future__ import annotations

import time
from typing import Any

from openai import OpenAI, APIError, BadRequestError, APITimeoutError

from observability.obs import span_step, safe_update_current_span_io, mark_error
from agent.confirmation_flow.state import ConfirmationState
from agent.confirmation_flow.models import ConfirmationInitialResult
from agent.linear_flow.utils import add_message

client = OpenAI(
    timeout=10,
    max_retries=1,
)

model = "gpt-4o"


def resolve_initial_llm(state: ConfirmationState) -> ConfirmationState:
    with span_step("confirmation_initial_llm_node", kind="node", node="confirmation_initial_llm_node"):
        with span_step(
            "llm_call",
            kind="llm",
            as_type="generation",
            model=model,
            node="confirmation_initial_llm_node",
        ) as _gen:
            messages = state.get("llm_messages", [])

            safe_update_current_span_io(
                input={
                    "query": state.get("query"),
                    "options": state.get("options"),
                    "messages": messages,
                },
                redact=True,
            )

            if not messages:
                # sanity guard, shouldn't happen now
                raise RuntimeError("resolve_initial_llm: llm_messages is empty")

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
                            "strict": False,
                        },
                    },
                )

                elapsed = time.time() - start
                print(f"confirmation initial LLM took {elapsed:.2f}s")
                print("LLM response (confirmation initial):", resp)

                result_model = ConfirmationInitialResult.model_validate_json(
                    resp.choices[0].message.content
                )
                result_dict = result_model.model_dump()
                print("confirmation initial result:", result_dict)

                safe_update_current_span_io(output=result_dict, redact=True)
                state["initial_result"] = result_dict

            except (APITimeoutError, APIError, BadRequestError) as e:
                # <<< CHANGE HERE: debug mode: show the real error and re-raise >>>
                print("\n[resolve_initial_llm] OpenAI error:", repr(e))
                mark_error(e, kind="LLMError", span=_gen)
                raise

            #print("\nResolve initial LLM state:", state)
            return state
