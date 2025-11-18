
from context.primitives.sender import SharedContactInfo

def handle_contacts(message: dict) -> str:
    contacts = message.get("contacts", [])
    if not contacts:
        return "לא צורפו אנשי קשר להודעה."

    contact_strings = []
    for contact in contacts:
        name = contact.get("name", {})
        phones = contact.get("phones", [])

        formatted_name = name.get("formatted_name", "")
        first_name = name.get("first_name", "")
        last_name = name.get("last_name", "")
        phone_numbers = [p.get("phone") for p in phones if p.get("phone")]

        name_str = formatted_name or f"{first_name} {last_name}".strip()
        phone_str = ", ".join(phone_numbers)

        line = f"שם: {name_str}, מספר: {phone_str}" if phone_str else f"שם: {name_str}"
        contact_strings.append(line.strip())

    return "\n".join(contact_strings)

from shared.user import get_user
from store.user import UserStore
from shared.user import userContextDict, normalize_recipient_id

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
