from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

# --- Internal override for testing ---
_current_time_override: Optional[datetime] = None

DEFAULT_TZ = ZoneInfo("Asia/Jerusalem")

# === Time Zone Conversion ===

# shared/time.py
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

def _parse_iso8601(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    s2 = s.strip()
    if s2.endswith("Z"):
        s2 = s2[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s2)
    except Exception:
        return None


def _user_tz(user_id: str) -> ZoneInfo:
    try:
        user = get_user(user_id)
        tz_name = getattr(getattr(user, "profile", None), "tz", None)
        return ZoneInfo(tz_name) if tz_name else DEFAULT_TZ
    except Exception:
        return DEFAULT_TZ


def _to_utc(dt: Optional[datetime], user_tz: ZoneInfo) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=user_tz).astimezone(timezone.utc)
    return dt.astimezone(timezone.utc)


from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

def to_user_timezone(dt: str | datetime, tz_name: str | None = "Asia/Jerusalem") -> datetime:
    # Accept ISO string as well
    if isinstance(dt, str):
        s = dt
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)

    # From here on, dt is definitely a datetime
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    try:
        tz = ZoneInfo(tz_name) if tz_name else timezone.utc
    except ZoneInfoNotFoundError:
        logger.warning("Timezone %s not found. Using UTC fallback.", tz_name)
        tz = timezone.utc

    return dt.astimezone(tz)


def now_iso_in_tz(tz_name: str | None) -> str:
    """Convenience: current time in tz, ISO 8601 with offset."""
    return to_user_timezone(datetime.now(timezone.utc), tz_name).isoformat()

def from_user_timezone(local_dt: datetime, tz_name: str = "Asia/Jerusalem") -> datetime:
    """Convert a local user datetime (naive or tz-aware) into UTC."""
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        print(f"[WARN] Timezone {tz_name} not found. Using UTC fallback.")
        tz = timezone.utc
    if local_dt.tzinfo is None:
        local_dt = local_dt.replace(tzinfo=tz)
    return local_dt.astimezone(timezone.utc)


# === Time Access ===

def utcnow() -> datetime:
    return _current_time_override or datetime.now(timezone.utc)


def set_fake_utcnow(fake_time: datetime) -> None:
    global _current_time_override
    _current_time_override = fake_time


def clear_fake_utcnow() -> None:
    global _current_time_override
    _current_time_override = None

# === Time Parsing ===

def parse_datetime(value: str) -> datetime:
    """Parse an ISO-8601 string. Supports trailing 'Z'. Returns a datetime; no timezone normalization here."""
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


# === Time Checks ===

def is_future(dt: datetime) -> bool:
    return dt > utcnow()

def is_past(dt: datetime) -> bool:
    return dt < utcnow()

def in_range(dt: datetime, start: datetime, end: datetime) -> bool:
    return start <= dt <= end

# === Utilities ===

def minutes_ago(minutes: int) -> datetime:
    return utcnow() - timedelta(minutes=minutes)

def minutes_from_now(minutes: int) -> datetime:
    return utcnow() + timedelta(minutes=minutes)

def days_ago(days: int) -> datetime:
    return utcnow() - timedelta(days=days)

def days_from_now(days: int) -> datetime:
    return utcnow() + timedelta(days=days)

# === Constants ===

ONE_MINUTE = timedelta(minutes=1)
ONE_HOUR = timedelta(hours=1)
ONE_DAY = timedelta(days=1)
ONE_WEEK = timedelta(weeks=1)
