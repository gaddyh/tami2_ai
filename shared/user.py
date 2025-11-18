from store.user import UserStore
from models.user import userContextDict, User, UserConfig, UserRuntime
from adapters.whatsapp.cloudapi.cloud_api_adapter import CloudAPIAdapter
adapter = CloudAPIAdapter()
from green_api.send import send_message
from observability.obs import span_attrs, mark_error  # NEW
def get_user(user_id: str) -> User | None:
    user = userContextDict.get(user_id)
    if user is None:
        user_store = UserStore(user_id)
        user = user_store.load()

    if user is None:
        return None
    
    return user

def create_user(user_id: str, message: str, sender_name: str) -> User | None:
    user = get_user(user_id)
    if user:
        return user

    userConfig = UserConfig(
        name=sender_name,
        timezone="Asia/Jerusalem",
        language="he",
        preferences={
            "nudge_minutes_before": None,
            "followup_minutes_after": None
        }
    )
    runtime = UserRuntime(
    )

    user = User(
        user_id=user_id,
        config=userConfig,
        runtime=runtime
    )
    user_store = UserStore(user_id)
    user_store.save(user)

    return user

import re
import phonenumbers

def normalize_recipient_id(s: str, default_region: str = "IL") -> str:
    """Return a normalized WhatsApp recipient chat_id for users or groups.

    - Groups: keep '<digits>[-digits]@g.us'
    - Users: normalize any valid phone (E.164) to '<digits>@c.us'
    - Accepts numbers from any country (uses default_region only as a fallback)
    """
    s = (s or "").strip()

    # Already a valid group chat id
    if re.fullmatch(r"\d{5,20}(?:-\d{5,20})?@g\.us", s):
        return s

    # Already a valid user chat id
    if re.fullmatch(r"\d{7,20}@c\.us", s):
        return s

    # Extract digits and parse with phonenumbers
    raw = s.lstrip("+").strip()
    try:
        parsed = phonenumbers.parse(raw, default_region)
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError(f"invalid number: {s}")
        e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        digits = e164.lstrip("+")  # WhatsApp prefers no '+'
        return f"{digits}@c.us"
    except phonenumbers.NumberParseException:
        raise ValueError(f"invalid recipient: {s}")

async def send_scheduled_message(sender_user_id: str, message: str, recipient_chat_id: str, recipient_name: str, sender_name: str):
    #from self ro bot?
    try:
        user = get_user(sender_user_id)
        if user and user.runtime.greenApiInstance and user.runtime.greenApiInstance.id:
            return send_message(
                user.runtime.greenApiInstance.id,
                user.runtime.greenApiInstance.token,
                recipient_chat_id,
                message,
            )
    except Exception as e:
        mark_error(e, kind="SchedulerError.greenapi_send")
        print(f"❌ GreenApi send failed for {sender_user_id}: {e}\nrecipient_chat_id: {recipient_chat_id}, message: {message}")
        
    parameters = [recipient_name, sender_name, message]
    return await adapter.send_template_message(recipient_chat_id, parameters)
    