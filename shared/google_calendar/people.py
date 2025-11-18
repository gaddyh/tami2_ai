import re
from typing import Callable, Optional, Tuple, List, Dict
import phonenumbers

# =========================
# Email helpers
# =========================

EMAIL_RE = re.compile(r"^[^@\s<>\"']+@[^@\s<>\"']+\.[^@\s<>\"']+$")
import re
import unicodedata
from typing import Dict, List

def _normalize_name_for_match(name: str) -> str:
    # Collapse whitespace + NFC to avoid Hebrew/emoji glitches
    name = unicodedata.normalize("NFC", name or "")
    name = " ".join(name.split())
    return name

def _normalize_email(email: str) -> str:
    email = (email or "").strip().lower()
    return email

_PHONE_KEEP = re.compile(r"[0-9+]+")
def _normalize_phone(phone: str) -> str:
    # Keep digits and a leading '+', strip spaces/dashes/() etc.
    phone = (phone or "").strip()
    if not phone:
        return ""
    # remove all non-digits except a single leading '+'
    if phone.startswith("+"):
        return "+" + "".join(ch for ch in phone[1:] if ch.isdigit())
    return "".join(ch for ch in phone if ch.isdigit())

def contacts_name_map(resolved: List[dict]) -> Dict[str, Dict[str, str]]:
    def score(r: dict) -> tuple[int, int, int]:
        # higher is better
        both = int(bool(r.get("email")) and bool(r.get("phone")))
        primary_sources = int(r.get("email_source") == "people.primary") + int(r.get("phone_source") == "people.primary")
        name_len = len(r.get("displayName", ""))
        return (both, primary_sources, name_len)

    # Work by normalized-name buckets to merge variants of the same name
    best_by_norm: Dict[str, dict] = {}

    for r in resolved:
        raw_name = (r.get("displayName") or "").strip()
        if not raw_name:
            continue

        norm_name = _normalize_name_for_match(raw_name)

        # Normalize email/phone for comparison & output
        email = _normalize_email(r.get("email", ""))
        phone = _normalize_phone(r.get("phone", ""))

        # create a shallow normalized view used for scoring/selection
        candidate = dict(r)
        candidate["displayName"] = raw_name  # keep original text for output
        candidate["email"] = email
        candidate["phone"] = phone

        if norm_name not in best_by_norm or score(candidate) > score(best_by_norm[norm_name]):
            best_by_norm[norm_name] = candidate

    # Build output keyed by the chosen record's original display name
    by_name: Dict[str, Dict[str, str]] = {}
    for cand in best_by_norm.values():
        key_name = cand["displayName"]
        by_name[key_name] = {
            "email": cand.get("email", "") or "",
            "phone": cand.get("phone", "") or "",
        }

    return by_name

def _pick_display_name(p: dict) -> str:
    names = p.get("names") or []
    primary = next((n for n in names if n.get("metadata", {}).get("primary")), None)
    n = primary or (names[0] if names else {})
    return (n.get("displayName") or n.get("unstructuredName") or n.get("displayNameLastFirst") or "ללא שם").strip()

def _normalize_email(raw: str) -> Optional[str]:
    if not raw:
        return None
    e = raw.strip().strip("<>").strip().strip('"').strip("'").lower()
    if EMAIL_RE.match(e):
        return e
    return None

def _is_noreply(email: str) -> bool:
    """Heuristic filter for automated senders."""
    local = (email or "").split("@", 1)[0]
    tokens = ("no-reply", "noreply", "do-not-reply", "donotreply")
    return any(t in local for t in tokens)

def _pick_primary_email(contact: dict) -> Optional[Tuple[str, str]]:
    emails = contact.get("emailAddresses") or []
    if not emails:
        return None

    primary = next((e for e in emails if e.get("metadata", {}).get("primary")), None)
    # 1) Prefer primary if valid & not a no-reply
    if primary:
        norm_primary = _normalize_email(primary.get("value", ""))
        if norm_primary and not _is_noreply(norm_primary):
            return norm_primary, "people.primary"

    # 2) Otherwise, first valid non-no-reply email in list order
    for e in emails:
        norm = _normalize_email(e.get("value", ""))
        if norm and not _is_noreply(norm):
            return norm, ("people.primary" if e is primary else "people.first")

    # 3) If only no-replys exist, fall back to primary if valid, else first valid
    if primary:
        if norm_primary:
            return norm_primary, "people.primary"
    for e in emails:
        norm = _normalize_email(e.get("value", ""))
        if norm:
            return norm, ("people.primary" if e is primary else "people.first")

    return None

# =========================
# Phone helpers
# =========================

def _normalize_phone(raw: str, default_region: str = "IL") -> Optional[str]:
    """
    Normalize a phone number into WhatsApp-ready form: 972522486836 (no '+').
    """
    if not raw:
        return None
    try:
        parsed = phonenumbers.parse(raw, default_region)
        if not phonenumbers.is_valid_number(parsed):
            return None
        e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        return e164.lstrip("+")  # WhatsApp expects no '+'
    except phonenumbers.NumberParseException:
        return None

def _extract_phone_fields(ph: dict) -> str:
    return ph.get("canonicalForm") or ph.get("value") or ""

def _pick_primary_phone(contact: dict) -> Optional[Tuple[str, str]]:
    phones = contact.get("phoneNumbers") or []
    if not phones:
        return None
    primary = next((ph for ph in phones if ph.get("metadata", {}).get("primary")), None)
    ordered = ([primary] if primary else []) + [ph for ph in phones if ph is not primary]
    for ph in ordered:
        norm = _normalize_phone(_extract_phone_fields(ph))
        if norm:
            return norm, ("people.primary" if ph is primary else "people.first")
    return None

# =========================
# Contact Resolution
# =========================

def resolve_contacts(
    people: List[dict],
    *,
    directory_lookup: Optional[Callable[[str], Optional[str]]] = None,
    manual_lookup: Optional[Callable[[Dict[str, str]], Optional[str]]] = None,
    phone_directory_lookup: Optional[Callable[[str], Optional[str]]] = None,
    phone_manual_lookup: Optional[Callable[[Dict[str, str]], Optional[str]]] = None,
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    resolved: List[Dict[str, str]] = []
    missing: List[Dict[str, str]] = []

    for p in people:
        resource = p.get("resourceName", "")
        display = _pick_display_name(p)

        # --- email ---
        email, email_src = (None, None)
        picked_email = _pick_primary_email(p)
        if picked_email:
            email, email_src = picked_email

        if not email and directory_lookup:
            d_email = _normalize_email(directory_lookup(display))
            if d_email:
                email, email_src = d_email, "workspace.directory"

        if not email and manual_lookup:
            m_email = _normalize_email(manual_lookup({"resourceName": resource, "displayName": display}))
            if m_email:
                email, email_src = m_email, "manual"

        # --- phone ---
        phone, phone_src = (None, None)
        picked_phone = _pick_primary_phone(p)
        if picked_phone:
            phone, phone_src = picked_phone

        if not phone and phone_directory_lookup:
            d_phone = _normalize_phone(phone_directory_lookup(display))
            if d_phone:
                phone, phone_src = d_phone, "workspace.directory"

        if not phone and phone_manual_lookup:
            m_phone = _normalize_phone(phone_manual_lookup({"resourceName": resource, "displayName": display}))
            if m_phone:
                phone, phone_src = m_phone, "manual"

        notes: List[str] = []
        if email and _is_noreply(email):
            notes.append("auto: no-reply address")

        record = {
            "resourceName": resource,
            "displayName": display,
            "email": email or "",
            "email_source": email_src or "",
            "phone": phone or "",
            "phone_source": phone_src or "",
            "status": "ok" if (email or phone) else "needs_contact",
        }
        if notes:
            record["notes"] = "; ".join(notes)

        if email or phone:
            resolved.append(record)
        else:
            missing.append(record)

    # Deduplicate by stable identity (resourceName), fallback to (email|phone)
    seen: Dict[str, Dict[str, str]] = {}
    for r in resolved:
        key = r.get("resourceName") or f"{r.get('email','')}|{r.get('phone','')}"
        prev = seen.get(key)
        if not prev or len(r.get("displayName", "")) > len(prev.get("displayName", "")):
            seen[key] = r
    deduped = list(seen.values())

    return deduped, missing

from typing import List, Dict, Tuple, Optional

# Priority for sources when choosing the single email/phone to keep
_SOURCE_RANK = {
    "people.primary": 3,
    "people.first": 2,
    "workspace.directory": 1,
    "manual": 0,
    "": -1,
    None: -1,
}

def _best_value(items: List[Tuple[str, str]]) -> Tuple[str, str, List[str]]:
    """
    items: list of (value, source). Returns (best_value, best_source, alternates_without_best)
    """
    if not items:
        return "", "", []
    best = max(items, key=lambda t: (_SOURCE_RANK.get(t[1], -1), len(t[0])))
    best_val, best_src = best
    alts = [v for (v, s) in items if v and v != best_val]
    return best_val, best_src or "", sorted(set(alts))

def _score_name(name: str) -> Tuple[int, int]:
    # Prefer longer, non-ASCII-rich names slightly (often more complete in People API)
    # (len, has_space)
    return (len(name or ""), 1 if " " in (name or "") else 0)

def merge_contacts(resolved: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Merge contacts that share the same email or phone into canonical records.
    Returns a list shaped like `resolved` but merged, with extras:
      - resourceNames: list[str]
      - alt_emails: list[str]
      - alt_phones: list[str]
    """
    if not resolved:
        return []

    # Union-Find over indices
    parent = list(range(len(resolved)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    # Index by email/phone (non-empty only)
    email_to_idx: Dict[str, int] = {}
    phone_to_idx: Dict[str, int] = {}

    for i, r in enumerate(resolved):
        e = (r.get("email") or "").strip()
        p = (r.get("phone") or "").strip()
        if e:
            if e in email_to_idx:
                union(i, email_to_idx[e])
            else:
                email_to_idx[e] = i
        if p:
            if p in phone_to_idx:
                union(i, phone_to_idx[p])
            else:
                phone_to_idx[p] = i

    # Group by root
    groups: Dict[int, List[int]] = {}
    for i in range(len(resolved)):
        root = find(i)
        groups.setdefault(root, []).append(i)

    merged: List[Dict[str, str]] = []
    for root, idxs in groups.items():
        # Aggregate fields in the group
        names: List[str] = []
        emails: List[Tuple[str, str]] = []
        phones: List[Tuple[str, str]] = []
        notes: List[str] = []
        resource_names: List[str] = []

        for i in idxs:
            r = resolved[i]
            names.append(r.get("displayName", "").strip())
            e = (r.get("email") or "").strip()
            if e:
                emails.append((e, r.get("email_source") or ""))
            p = (r.get("phone") or "").strip()
            if p:
                phones.append((p, r.get("phone_source") or ""))

            if r.get("notes"):
                notes.append(r["notes"])
            if r.get("resourceName"):
                resource_names.append(r["resourceName"])

        # Choose canonical name
        display = max((n for n in names if n), default="ללא שם", key=_score_name)

        # Choose canonical email/phone (and collect alternates)
        email, email_src, alt_emails = _best_value(emails)
        phone, phone_src, alt_phones = _best_value(phones)

        record = {
            "resourceName": resource_names[0] if resource_names else "",
            "displayName": display,
            "email": email,
            "email_source": email_src,
            "phone": phone,
            "phone_source": phone_src,
            "status": "ok" if (email or phone) else "needs_contact",
            "resourceNames": sorted(set(resource_names)),
        }
        if alt_emails:
            record["alt_emails"] = sorted(set(alt_emails))
        if alt_phones:
            record["alt_phones"] = sorted(set(alt_phones))
        if notes:
            record["notes"] = "; ".join(sorted(set(notes)))

        merged.append(record)

    return merged
