import csv
from pathlib import Path

# ── Constants ───────────────────────────────────────────────
_CUSTOMERS_FILE = Path(__file__).parent / "customers1.csv"
_PRODUCTS_FILE = Path(__file__).parent / "products.txt"

# ── Internal loader ─────────────────────────────────────────
def _load_customers():
    customers = {}
    with open(_CUSTOMERS_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)  # <-- no delimiter (defaults to comma)
        for row in reader:
            # skip blank id cells
            raw_id = (row.get("מס. לקוח") or "").strip()
            if not raw_id:
                continue
            try:
                customer_id = int(raw_id)
            except ValueError:
                continue
            customers[customer_id] = {
                "name": (row.get("שם לקוח") or "").strip(),
                "address": (row.get("עיר") or "").strip(),
            }
    return customers

def get_customer_id_by_name(name: str) -> int | None:
    name = name.strip()
    for cid, data in CUSTOMERS.items():
        if data["name"] == name:
            return cid
    return None

def get_product_id_by_name(name: str) -> int | None:
    name = name.strip()
    for pid, desc in PRODUCTS.items():
        if desc == name:
            return pid
    return None


def _load_products():
    products = {}
    with open(_PRODUCTS_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            try:
                product_id = int(row["מקט"])
            except ValueError:
                continue
            products[product_id] = row["תאור"]
    return products

# ── Load once at import ─────────────────────────────────────
CUSTOMERS = _load_customers()
CUSTOMERS_STRING = "id | name | address\n" + "\n".join(
    f"{data.get('name','').strip()}"
    #f"{cid} | {data.get('name','').strip()} | {data.get('address','').strip()}"
    for cid, data in sorted(CUSTOMERS.items())
)

PRODUCTS = _load_products()
PRODUCTS_STRING = "\n".join(
    f"{name}"
    for name in PRODUCTS.values()
)


if __name__ == "__main__":
    print(CUSTOMERS_STRING)
