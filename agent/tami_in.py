# app.py
from __future__ import annotations
from typing import Optional

from models.input import In
from models.decision import DecisionOutcome, TargetAgent, Decision
from route.route_input import route_input
from dedupe.cache import idempotency_cache
from langfuse import observe
from observability.telemetry import langfuse, set_common_trace_attrs, mark_error
from observability.obs import span_attrs, span_step, safe_update_current_span_io
from models.agent_output import TamiOutput
from agents import RunResult
from tools.base import instrument_io
from agent.core import run_agent

class Out(Decision):
    trace_id: Optional[str] = None

@instrument_io(
    name="process_input",
    meta={"agent": "tami", "operation": "process_input", "tool": "process_input", "schema": "In.v1"},
    input_fn=lambda inp: {
        "user_id": inp.user_id,
        # ↓ serialize Pydantic model for the instrumentation layer
        "inp": (inp.model_dump() if hasattr(inp, "model_dump")
                  else inp.dict() if hasattr(inp, "dict")
                  else inp)
    },
    output_fn=lambda result: result,
    redact=True,
)
async def process_input(inp: In) -> Out | TamiOutput:
    with set_common_trace_attrs(inp, extra_metadata={"agent.root": "input"}):
        with span_step("route.route_input", kind="RouteError", operation="route") as s:
            safe_update_current_span_io(input=inp)  # optional (keeps block-local IO too)

            route_result = route_input(inp)

            safe_update_current_span_io(
                output=route_result,
            )
            langfuse.update_current_span(metadata={
                "status": "ok",
                "decision": getattr(route_result.decision, "value", str(route_result.decision)),
                "target_agent": getattr(route_result.targetAgent, "value", str(route_result.targetAgent)),
            })

        if route_result.decision is DecisionOutcome.IGNORE:
            out = Out(
                outcome=DecisionOutcome.IGNORE,
                reason="duplicate",
                confidence=1.0,
                tags=[],
                target_agent=None,
                idempotency_key_used=None,
                normalized_text=None,
                trace_id=None,
            )
            try:
                out.trace_id = langfuse.get_current_trace_id()
            except Exception:
                out.trace_id = None

            safe_update_current_span_io(output=out)
            return out

        idem = inp.idempotency_key or (inp.source_ids.whatsapp_msg_id if inp.source_ids else None)
        if idem:
            with span_step("dedupe.mark", kind="CacheMarkError", key="idempotency", operation="mark") as s:
                langfuse.update_current_span(metadata={"idempotency_key": idem})
                idempotency_cache.mark(idem)
                langfuse.update_current_span(metadata={"status": "ok", "marked": True})

        target = route_result.targetAgent or TargetAgent.PERSONAL_ASSISTANT
       
        agent_result: RunResult = await run_agent(inp, target_agent=target)
        tamiOutput: TamiOutput = agent_result.final_output
        try:
            tamiOutput.trace_id = langfuse.get_current_trace_id()
        except Exception:
            tamiOutput.trace_id = None

        safe_update_current_span_io(output=tamiOutput)
        return tamiOutput.final_output


# run_input.py
import uuid
from models.input import In, Source, Category


text = "מה המשימות שלי?"
text = "תזכירי לי עוד שעה לעשן"
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(".venv/.env")

    inp = In(
        user_id="user_id1",
        user_name="user_name1",
        thread_id="thread_id1",
        text=text,
        source=Source.WHATSAPP,
        category=Category.USER_REQUEST,
        input_id=uuid.uuid4().hex,
        idempotency_key="wa_msg_12345",
        tz="Asia/Jerusalem",
        locale="he-IL",
    )

    
    #out = process_input(inp)
    #print("OK ✅ process_input returned")
    #print("result:", out)
    #print("trace_id:", out.trace_id)

    inp.text = "תיצור לי אירוע ב14 לנקות את האוטו"
    inp.text = "מה המשימות שלי היום?"
    inp.text = "מה האירועים שלי היום?"
    inp.text = "תשלחי בעשר בבוקר לאורי גיטרה הודעה. מה קורה יא גבר?"

    inp.text = "מה הדבר האחרון שכתבתי לשיוש?"
    inp.text = "מה סגרנו בסוף בתמי שלנו?"
    inp.text = "תסגרי את כל המשימות שלי"
    inp.text = "תירצי לי משימה לבדוק את האוטו"
    inp.text = "תחפשי בגוגל מה הכתובת של שרוני מוטורס?"

    inp.text = "add to my calendar the following all day events:\n1. test 18.11\n2. test 19.11\n3. test 20.11"

    inp.text = "מה המשימות שלי ?"
    inp.idempotency_key = "wa_msg_12346"
    inp.user_id = "972546610653"
    inp.user_name = "me"
    inp.thread_id = "thread_id2"




    import asyncio
    out = asyncio.run(process_input(inp))
    print("OK ✅ process_input returned")
    print("result:", out)

   