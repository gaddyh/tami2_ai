from google.cloud import firestore
from db.base import db

def save_customer_alias_mapping(alias: str, canonical: str):
    # Optional: check if alias already exists to avoid duplicates
    existing = (
        db.collection("customer_aliases")
        .where("alias", "==", alias)
        .limit(1)
        .stream()
    )
    for doc in existing:
        doc.reference.update({"canonical": canonical})
        print(f"Updated mapping: {alias} -> {canonical}")
        return

    # Create new doc with auto ID
    ref = db.collection("customer_aliases").document()
    ref.set({
        "alias": alias,
        "canonical": canonical
    })
    print(f"Saved mapping: {alias} -> {canonical}")

def get_customer_canonical_name(alias: str) -> str | None:
    query = db.collection("customer_aliases").where("alias", "==", alias).limit(1)
    docs = query.stream()
    for doc in docs:
        return doc.to_dict().get("canonical")
    return None

if __name__ == "__main__":
    save_customer_alias_mapping("שיח חליל", "אחמד עבדלה (שייח חליל) - אעבלין")