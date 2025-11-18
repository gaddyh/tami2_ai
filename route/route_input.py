
from models.decision import DecisionOutcome, TargetAgent
from models.input import In, Category
from typing import Optional
from dataclasses import dataclass
from dedupe.cache import idempotency_cache

MONITORED_CHAT_IDS = [
    "1234567890",
    "0987654321",
]

@dataclass
class RouteResult:
    decision: DecisionOutcome
    targetAgent: Optional[TargetAgent] = None

def route_input(payload: In) -> RouteResult:

      # 0) Idempotency hard stop via cache
    idem = payload.idempotency_key or (payload.source_ids.whatsapp_msg_id if payload.source_ids else None)
    if idem and idempotency_cache.seen(idem):
        return RouteResult(
            decision=DecisionOutcome.IGNORE,
        )
    
    if payload.category == Category.INCOMING_MSG:
        if payload.chat_id in MONITORED_CHAT_IDS:
            return RouteResult(
                decision=DecisionOutcome.ROUTE,
                targetAgent=TargetAgent.MONITOR,
            )
        return RouteResult(
            decision=DecisionOutcome.IGNORE,
        )

    if payload.category == Category.SCHEDULED_TRIGGER:
        return RouteResult(
            decision=DecisionOutcome.ROUTE,
            targetAgent=TargetAgent.SCHEDULER,
        )

    return RouteResult(
        decision=DecisionOutcome.ROUTE,
        targetAgent=TargetAgent.PERSONAL_ASSISTANT,
    )