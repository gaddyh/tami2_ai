from dataclasses import dataclass
from shared.observability.tracing import Tracer
from context.message.raw_message import RawMessage
from context.message.identity import BotIdentity

@dataclass
class Interaction:
    message: RawMessage
    identity: BotIdentity
    chat_name: str
    is_group: bool
    is_self_group: bool
    tracer: Tracer