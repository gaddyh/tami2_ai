# linear_flow/nodes/responder_llm.py
import time
from openai import OpenAI, APIError, BadRequestError, APITimeoutError
from agent.linear_flow.state import LinearAgentState
from agent.linear_flow.models import LinearAgentResponse
from observability.obs import span_step, safe_update_current_span_io, mark_error
from agent.linear_flow.utils import add_message

client = OpenAI(timeout=10, max_retries=1)
model = "gpt-4o"


def responder_llm(state: LinearAgentState) -> LinearAgentState:
    with span_step("responder_llm_node", kind="node", node="responder_llm_node"):
        with span_step(
            "llm_call",
            kind="llm",
            as_type="generation",
            model=model,
            node="responder_llm_node",
        ) as _gen:
            llm_messages = state.get("llm_messages", [])

            safe_update_current_span_io(
                input={"llm_messages": llm_messages},
                redact=True,
            )

            start = time.time()
            try:
                schema = LinearAgentResponse.model_json_schema()

                resp = client.chat.completions.create(
                    model=model,
                    messages=llm_messages,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "LinearAgentResponse",
                            "schema": schema,
                            "strict": False,
                        },
                    },
                )

                elapsed = time.time() - start
                print(f"Responder LLM parse took {elapsed:.2f}s")
                #print("LLM response:", resp)

                parsed = LinearAgentResponse.model_validate_json(
                    resp.choices[0].message.content
                )

                # Log parsed output (response OR followup_message)
                safe_update_current_span_io(
                    output=parsed.model_dump(),
                    redact=True,
                )

                # Normalize into state:
                # Normal final answer
                state["response"] = parsed.response
                state["is_followup_question"] = parsed.is_followup_question
                state["needs_person_resolution"] = parsed.needs_person_resolution
                state["person_resolution_items"] = parsed.person_resolution_items
                add_message("assistant", parsed.response, state)

            except (APITimeoutError, APIError, BadRequestError) as e:
                fallback = "משהו השתבש, נסה לנסח שוב."
                state["response"] = fallback
                state["is_followup_question"] = False
                state["needs_person_resolution"] = False
                state["person_resolution_items"] = None
                add_message("assistant", fallback, state)
                state["status"] = "error"
                mark_error(e, kind="LLMError", span=_gen)

            return state
