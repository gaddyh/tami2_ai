from agent.linear_flow.state import LinearAgentState
from observability.obs import span_step, safe_update_current_span_io, mark_error
from agent.linear_flow.models import LinearAgentPlan
from openai import OpenAI
from openai import APIError, BadRequestError, APITimeoutError
import time
from typing import Any
from agent.linear_flow.utils import add_message

client = OpenAI(
        timeout=10,      # seconds, pick what you like
        max_retries=1,   # don't keep retrying a bad request
    )
    
model = "gpt-4o"

def planner_llm(state: LinearAgentState) -> LinearAgentState:
    with span_step("planner_llm_node", kind="node", node="planner_llm_node"):
        # inner span as generation (LLM call)
        with span_step(
            "llm_call",
            kind="llm",
            as_type="generation",
            model=model,           # or state.model_name
            node="planner_llm_node",
        ) as _gen:
        # log input
            safe_update_current_span_io(input={"context": state["context"], "messages": state["llm_messages"]}, redact=True)
            # ---------- Call LLM with Structured Outputs ----------
            start = time.time()
            try:
                schema = LinearAgentPlan.model_json_schema()

                resp = client.chat.completions.create(
                    model=model,
                    messages=state["llm_messages"],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "LinearAgentPlan",
                            "schema": schema,
                            "strict": False,   # <-- FIX: non-strict so args: Dict[str,Any] is allowed
                        },
                    },
                )

                elapsed = time.time() - start
                # optional debug:
                print(f"LLM parse took {elapsed:.2f}s")

                #print("llm messages:", state["llm_messages"])
                #print("LLM response:", resp)
                plan = LinearAgentPlan.model_validate_json(resp.choices[0].message.content)

                # log output
                safe_update_current_span_io(output=plan.model_dump(), redact=True)
                state["actions"] = plan.actions
                state["followup_message"] = plan.followup_message

            except (APITimeoutError, APIError, BadRequestError) as e:
                # Fallback: no tools, simple error/clarification message
                state["actions"] = []
                state["followup_message"] = "משהו השתבש, נסה לנסח שוב."
                add_message("assistant", state["followup_message"], state)
                state["status"] = "error"
                # You can also log `e` somewhere
                mark_error(e, kind="LLMError", span=_gen)

            return state