from google.cloud import firestore
from db.base import db
from typing import Optional, Dict, Any

def save_product_alias(
    alias: str,
    canonical_product_id: str,
    *,
    canonical_product_name: Optional[str] = None,
    customer_id: Optional[str] = None,
) -> None:
    """
    Upsert mapping for alias -> canonical product.
    If customer_id is provided, it creates/updates a customer-specific override.
    Otherwise it creates/updates a global mapping.
    """
    col = db.collection("product_aliases")
    # Try to find existing by (alias, customer_id)
    q = (
        col.where("alias", "==", alias)
           .where("customer_id", "==", customer_id)  # None means global
           .limit(1)
           .stream()
    )
    try:
        doc = next(q)
        doc.reference.update({
            "canonical_product_id": canonical_product_id,
            "canonical_product_name": canonical_product_name,
            "updated_at": firestore.SERVER_TIMESTAMP,
        })
        return
    except StopIteration:
        pass

    # Create new (auto-ID)
    ref = col.document()
    ref.set({
        "alias": alias,
        "canonical_product_id": canonical_product_id,
        "canonical_product_name": canonical_product_name,
        "customer_id": customer_id,  # None => global
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    })

def get_canonical_product(
    alias: str,
    *,
    customer_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Resolve alias to canonical product.
    1) Try customer-specific override (alias + customer_id)
    2) Fallback to global mapping (alias + customer_id == None)
    Returns a dict with canonical fields or None.
    """
    col = db.collection("product_aliases")

    # 1) customer-specific
    q1 = (
        col.where("alias", "==", alias)
           .where("customer_id", "==", customer_id)
           .limit(1)
           .stream()
    )
    for doc in q1:
        d = doc.to_dict()
        return {
            "canonical_product_id": d.get("canonical_product_id"),
            "canonical_product_name": d.get("canonical_product_name"),
            "customer_id": d.get("customer_id"),
            "scope": "customer",
        }

    # 2) global
    q2 = (
        col.where("alias", "==", alias)
           .where("customer_id", "==", None)
           .limit(1)
           .stream()
    )
    for doc in q2:
        d = doc.to_dict()
        return {
            "canonical_product_id": d.get("canonical_product_id"),
            "canonical_product_name": d.get("canonical_product_name"),
            "customer_id": d.get("customer_id"),
            "scope": "global",
        }

    return None

if __name__ == "__main__":
    save_product_alias("מטילות", "", canonical_product_name="מטילות ניבה")
    


