from db.base import db
COLLECTION_NAME = "new_waiting_users"

# --- Save new user ---
def save_user_chat_id(chat_id: str) -> str:
    """
    Saves a user phone number into Firestore under collection 'users'.
    Returns the generated document ID.
    """
    chat_id = chat_id.strip()

    doc_ref = db.collection(COLLECTION_NAME).document()
    doc_ref.set({"chat_id": chat_id})
    return doc_ref.id

# --- Get user by phone ---
def get_user_chat_id(chat_id: str) -> dict | None:
    """
    Retrieves a user document by phone number.
    Returns the document data (dict) if found, else None.
    """
    chat_id = chat_id.strip()
    users_ref = db.collection(COLLECTION_NAME)
    query = users_ref.where("chat_id", "==", chat_id).limit(1).stream()

    for doc in query:
        return {"id": doc.id, **doc.to_dict()}

    return None

# Example usage
if __name__ == "__main__":
    # Save a user
    user_id = save_user_chat_id("1234567")
    print(f"User saved with ID: {user_id}")

    # Retrieve user by phone
    user_data = get_user_chat_id("1234567")
    if user_data:
        print(f"User found: {user_data}")
    else:
        print("User not found.")
