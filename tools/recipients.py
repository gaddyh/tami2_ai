import unicodedata
from datetime import datetime

def now_iso() -> str:
    return datetime.utcnow().isoformat()

from rapidfuzz import fuzz
import unicodedata
from agents import RunContextWrapper
from models.app_context import AppCtx
from tools.base import function_tool, span_attrs, mark_error, summarize
from observability.obs import instrument_io
import unicodedata
from rapidfuzz import fuzz

def _normalize_name(name: str) -> str:
    # NFC + strip + casefold (handles Latin; harmless for Hebrew)
    return unicodedata.normalize("NFC", (name or "").strip()).casefold()

def _match_score(target: str, candidate: str) -> float:
    if not target or not candidate:
        return 0.0
    score = fuzz.token_sort_ratio(target, candidate)  # works fine for Hebrew too
    return score / 100.0

def _best_chat_id(phone: str | None) -> str | None:
    phone = (phone or "").strip()
    if not phone:
        return None
    return phone if phone.endswith("@c.us") else f"{phone}@c.us"

def _get_candidate_recipient_info(user_id: str, name: str, limit: int = 8):
    """
    Returns: name, candidates, count, ts:
    {
        "name": raw_query,
        "candidates": [cand][:limit],
        "count": 1,
        "ts": now_iso(),
    }
    """
    from shared.user import get_user

    def _rec_kind_and_ids(rec: dict[str, str]) -> tuple[str, str | None, str | None, str | None]:
        """
        Return (kind, chat_id, phone, email)
          kind: 'group' | 'contact'
          chat_id: JID for group (@g.us) or person (@c.us) if derivable
        """
        phone = (rec.get("phone") or "").strip()
        email = (rec.get("email") or "").strip().lower() or None

        # Prefer explicit group signals
        group_id = (rec.get("group_id") or rec.get("groupId") or rec.get("chat_id") or "").strip()
        if group_id.endswith("@g.us"):
            return "group", group_id, None, None

        # Some stores keep group_name + group_id without 'chat_id'
        if group_id and "@g.us" in group_id:
            return "group", group_id, None, None

        # Person
        chat_id = _best_chat_id(phone) if phone else None
        return "contact", chat_id, (phone or None), email

    def _mk_candidate(display_name: str, rec: dict[str, str], score: float) -> dict:
        kind, chat_id, phone, email = _rec_kind_and_ids(rec)
        base = {
            "display_name": display_name,
            "score": round(score, 3),
            "type": kind,
            "chat_id": chat_id,   # for groups: the @g.us JID; for people: @c.us if phone exists
            "phone": phone,
            "email": email,
        }
        if kind == "group":
            # convenience alias; some callers prefer 'group_id'
            base["group_id"] = chat_id
        return base

    if not name:
        return {"name": name, "candidates": [], "count": 0, "ts": now_iso()}

    user = get_user(user_id)
    if not user or not getattr(user.runtime, "contacts", None):
        return {"name": name, "candidates": [], "count": 0, "ts": now_iso()}

    # contacts may include both people and groups
    contacts: dict[str, dict[str, str]] = user.runtime.contacts

    raw_query = name.strip()
    norm_query = _normalize_name(raw_query)

    # ---------- 1) EXACT MATCH ----------
    for display_name, rec in contacts.items():
        if _normalize_name(display_name) == norm_query:
            cand = _mk_candidate(display_name, rec, score=1.0)
            return {
                "name": raw_query,
                "candidates": [cand][:limit],
                "count": 1,
                "ts": now_iso(),
            }

    # ---------- 2) SUBSTRING MATCH (if any → NO fuzzy) ----------
    substring_hits: list[dict] = []
    for display_name, rec in contacts.items():
        norm_display = _normalize_name(display_name)
        if norm_query in norm_display:
            starts = norm_display.startswith(norm_query)
            excess_len = max(0, len(norm_display) - len(norm_query))
            cand = _mk_candidate(display_name, rec, score=(0.95 if starts else 0.9))
            cand["_starts"] = starts
            cand["_excess_len"] = excess_len
            # prefer items with a resolvable chat_id
            cand["_has_chat_id"] = bool(cand.get("chat_id"))
            substring_hits.append(cand)

    if substring_hits:
        substring_hits.sort(
            key=lambda x: (
                x["_starts"],          # startswith first
                x["_has_chat_id"],     # resolvable JID next
                -x["_excess_len"],     # shorter excess length wins
                x["type"] == "group",  # mild nudge: groups after personal if all else equal
            ),
            reverse=True,
        )
        # strip helper keys
        for c in substring_hits:
            c.pop("_starts", None); c.pop("_excess_len", None); c.pop("_has_chat_id", None)

        candidates = substring_hits[:limit]
        return {
            "name": raw_query,
            "candidates": candidates,
            "count": len(candidates),
            "ts": now_iso(),
        }

    # ---------- 3) FUZZY MATCH ----------
    fuzzy_hits: list[dict] = []
    for display_name, rec in contacts.items():
        norm_display = _normalize_name(display_name)
        score = _match_score(norm_query, norm_display)
        if score <= 0:
            continue

        cand = _mk_candidate(display_name, rec, score=score)
        # Skip totally unresolved entries (no phone, no group id)
        if not cand.get("chat_id") and not cand.get("phone"):
            continue
        fuzzy_hits.append(cand)

    fuzzy_hits.sort(
        key=lambda x: (
            x["score"],
            bool(x.get("chat_id")),   # resolvable JID preferred
            x["type"] != "group",     # mild preference: contacts before groups if tied
        ),
        reverse=True,
    )
    candidates = fuzzy_hits[:limit]

    return {
        "name": raw_query,
        "candidates": candidates,
        "count": len(candidates),
        "ts": now_iso(),
    }


@function_tool(strict_mode=True)
@instrument_io(
    name="tool.get_candidates_recipient_info",
    meta={"agent": "tami", "operation": "tool", "tool": "get_candidates_recipient_info", "schema": "ReminderItem.v1"},
    input_fn=lambda ctx, name, include_email_for_event_invite: {"user_id": ctx.context.user_id, "name": name, "include_email_for_event_invite": include_email_for_event_invite},
    output_fn=summarize,
    redact=True,
)
def get_candidates_recipient_info(ctx: RunContextWrapper[AppCtx], name: str, include_email_for_event_invite: bool = False):
    masked = name[:2] + "…" if name else ""
    with span_attrs("tool.get_candidates_recipient_info", agent="tami", operation="tool", tool="get_candidates_recipient_info") as s:
        s.update(input={"name_len": len(name or ""), "name_preview": masked})
        try:
            out = _get_candidate_recipient_info(user_id=ctx.context.user_id, name=name)
            if not include_email_for_event_invite:
                out["candidates"] = [{"display_name": c["display_name"], "score": c["score"], "type": c["type"], "chat_id": c["chat_id"], "phone": c["phone"]} for c in out["candidates"]]
            s.update(output=summarize(out)); return out
        except Exception as e:
            mark_error(e, kind="ToolError.get_candidate_recipient_info", span=s); raise
