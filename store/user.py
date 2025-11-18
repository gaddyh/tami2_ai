from models.user import User
from db.base import db

class UserStore:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.db = db
        self.doc_ref = self.db.collection("users").document(user_id)

    def save(self, user: User):
        self.doc_ref.set(user.model_dump(exclude={"runtime": {"chatIndexStore"}}), merge=True)

    def load(self) -> User | None:
        doc = self.doc_ref.get()
        if doc.exists:
            return User(**doc.to_dict())
        return None

    def delete(self):
        self.doc_ref.delete()