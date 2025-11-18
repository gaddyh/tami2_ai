from typing import Optional, Dict
from shared.user import get_user, create_user
from store.user import UserStore

def save_contacts_to_runtime(user_id: str, by_name: Dict[str, Dict[str, Optional[str]]]) -> int:
    user = get_user(user_id)
    if user is None:
        user = create_user(user_id, "", "")

    # Ensure runtime/contacts dicts exist
    if getattr(user, "runtime", None) is None:
        user.runtime = type("Runtime", (), {})()  # or your actual Runtime model
    if not getattr(user.runtime, "contacts", None):
        user.runtime.contacts = {}

    # Merge by name: don't overwrite a non-empty value with an empty one
    for name, rec in by_name.items():
        name = (name or "").strip()
        if not name:
            continue
        email = (rec.get("email") or "").strip().lower() or None
        phone = (rec.get("phone") or "").strip() or None

        existing = user.runtime.contacts.get(name, {})
        final_email = email or existing.get("email") or None
        final_phone = phone or existing.get("phone") or None

        user.runtime.contacts[name] = {
            "email": final_email,
            "phone": final_phone,
        }

    total = len(user.runtime.contacts)
    print("save_contacts_to_runtime: total=", total)

    try:
        data = user.model_dump()
        print("about to save user data:", list(data.keys()))
        rc = data.get("runtime", {}).get("contacts", {})
        sample = dict(list(rc.items())[:3]) if isinstance(rc, dict) else {}
        print("runtime.contacts sample:", sample)

        store = UserStore(user_id)
        store.doc_ref.set(data, merge=True)
        print("Firestore save succeeded for user:", user_id)
    except Exception as e:
        import traceback
        print("❌ Firestore save failed:", e)
        traceback.print_exc()

    return total
