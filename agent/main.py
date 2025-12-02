# react_agent_cli.py

#from bidi.algorithm import get_display
from shared.time import to_user_timezone, utcnow
from context.message.raw_message import RawMessage
from models.user import User
from context.primitives.sender import SenderInfo
from context.primitives.replies_info import ContentInfo
from models.user import UserConfig, UserRuntime
from shared.time import to_user_timezone, utcnow
from shared.whisper_stt_facebook import transcribe_facebook_audio
from context.primitives.sender import SharedContactInfo
from models.input import In, Source, Category
from agent.tami.main import process_input
from tools.base import instrument_io
get_display = lambda x: x

import uuid
from shared.user import get_user
from store.user import UserStore
from shared.user import userContextDict, normalize_recipient_id
from langfuse import observe

def format_shared_contact(contact: SharedContactInfo, user_id: str) -> str:
    if not contact:
        return ""
    parts = []
    
    if contact.formatted_name:
        parts.append(f"שם: {contact.formatted_name}")
    elif contact.first_name or contact.last_name:
        full_name = f"{contact.first_name or ''} {contact.last_name or ''}".strip()
        parts.append(f"שם: {full_name}")

    name = contact.formatted_name or f"{contact.first_name or ''} {contact.last_name or ''}".strip()
    chat_id = normalize_recipient_id(contact.phone)
    user = get_user(user_id)
    contact1 = user.runtime.contacts.get(name, {})
    contact1["phone"] = chat_id.split("@")[0]
    user.runtime.contacts[name] = contact1

    UserStore(user_id).save(user)
    userContextDict[user_id] = user

    if contact.phone:
        parts.append(f"מספר: {contact.phone}")

    return ", ".join(parts) if parts else ""

def handle_media(content):
    if content.type == "audio":
        text = transcribe_facebook_audio(content.media)
        content.text = f"stt: {text}"

@observe(name="user-input")  # root trace for this request
@instrument_io(
    name="handleUserInput",
    meta={"agent": "tami", "operation": "handleUserInput", "tool": "handleUserInput", "schema": "RawMessage.v1"},
    input_fn=lambda rawMessage, user: {
        "user_id": user.user_id,
        # ↓ serialize Pydantic model for the instrumentation layer
        "rawMessage": (rawMessage.model_dump() if hasattr(rawMessage, "model_dump")
                  else rawMessage.dict() if hasattr(rawMessage, "dict")
                  else rawMessage)
    },
    output_fn=lambda result: result,
    redact=True,
)
async def handleUserInput(rawMessage:RawMessage, user:User):
    handle_media(rawMessage.content)
    contact = format_shared_contact(rawMessage.content.contact, user.user_id)
    if contact:
        text = (rawMessage.content.text + "\n") if rawMessage.content.text else ""
        rawMessage.content.text = text + contact

    if rawMessage.content.button_reply:
        br = rawMessage.content.button_reply
        rawMessage.content.text = f"{br.text}"

    from shared.time import now_iso_in_tz

    inp = In(
        user_id=user.user_id,
        user_name=user.config.name,
        thread_id=rawMessage.chat_id,
        current_datetime=now_iso_in_tz(user.config.timezone),
        text=rawMessage.content.text,
        source=Source.WHATSAPP,
        category=Category.USER_REQUEST,
        input_id=uuid.uuid4().hex,
        idempotency_key=rawMessage.idempotency_key,
        tz=user.config.timezone,
        locale=user.config.language,
    )

    result = process_input(inp)
    print(f"result:\n {result}")
    return result

import asyncio

async def main():
    while True:
        try:
            user_input = input("You: ")
            print(f"You: {get_display(user_input)}")
            if user_input.strip().lower() in {"exit", "quit"}:
                break

            injected_prefix = f"השעה כעת היא {to_user_timezone(utcnow())}. "
            user_input = injected_prefix + user_input

            result = await handleUserInput(
                RawMessage(
                    SenderInfo(name="You", chatId="972546610653", isSelfSender=False, phone=""),
                    ContentInfo(type="text", text=user_input),
                    "972546610653", "", message_data={}, idempotency_key=uuid.uuid4().hex
                ),
                User(
                    config=UserConfig(name="You", timezone="Asia/Jerusalem", language="he"),
                    runtime=UserRuntime(),
                    user_id="972546610653"
                )
            )

            print(f"Agent: {get_display(result)}")

        except Exception as e:
            print(f"[Error] {e}")

if __name__ == "__main__":
    asyncio.run(main())
