# google_calendar/calendar.py

from googleapiclient.discovery import build
from typing import Optional, List
from google.oauth2.credentials import Credentials
from shared.google_calendar.token_cache import get_cached_credentials
from fastapi import APIRouter
from shared import time
from shared.google_calendar.people import resolve_contacts, merge_contacts, contacts_name_map
from store.people_store import save_contacts_to_runtime

calendar_router = APIRouter()

def utcnow_rfc3339() -> str:
    """Return current UTC time in RFC3339 format without microseconds, ending with Z."""
    return time.utcnow().replace(microsecond=0).isoformat().replace("+00:00", "Z")

@calendar_router.get("/google/events")
async def get_upcoming_events(user_id: str, max_results: int = 10):
    time_min = utcnow_rfc3339()
    try:
        events = pull_upcoming_events(user_id, time_min, max_results)
        return {"events": events}
    except Exception as e:
        return {"error": str(e)}

def pull_upcoming_events(
    user_id: str,
    time_min: Optional[str] = None,
    max_results: int = 10
) -> List[dict]:
    creds = get_cached_credentials(user_id)
    if not creds:
        raise Exception("Missing or invalid Google credentials")

    service = build("calendar", "v3", credentials=creds)

    if time_min is None:
        time_min = utcnow_rfc3339()

    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=time_min,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime"
        )
        .execute()
    )
    return events_result.get("items", [])
from typing import Optional, List, Dict
import time
import random
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials

# Fetch all contacts with only the fields you actually use.
# - personFields: names, emailAddresses, phoneNumbers
# - fields (partial response): include metadata.primary and canonicalForm explicitly
def fetch_contacts(user_id: str, credentials: Optional[Credentials] = None) -> List[Dict]:
    if not credentials:
        creds = get_cached_credentials(user_id)
        if not creds:
            raise Exception("Missing or invalid Google credentials")
    else:
        creds = credentials

    service = build("people", "v1", credentials=creds)

    all_connections: List[Dict] = []
    page_token: Optional[str] = None

    # Partial response mask keeps payload lean and ensures presence of metadata.primary + canonicalForm
    fields_mask = (
        "connections("
        "resourceName,"
        "names(displayName,displayNameLastFirst,unstructuredName,metadata(primary)),"
        "emailAddresses(value,metadata(primary)),"
        "phoneNumbers(value,canonicalForm,metadata(primary))"
        "),nextPageToken"
    )

    # Simple bounded exponential backoff for transient errors
    def _execute_with_retry(req, max_attempts: int = 5):
        delay = 0.5
        for attempt in range(1, max_attempts + 1):
            try:
                return req.execute(num_retries=0)  # we handle retries ourselves
            except HttpError as e:
                status = getattr(e.resp, "status", None)
                if status in (429, 500, 502, 503, 504) and attempt < max_attempts:
                    time.sleep(delay + random.uniform(0, 0.2))
                    delay = min(delay * 2, 8.0)
                    continue
                raise

    while True:
        request = (
            service.people()
            .connections()
            .list(
                resourceName="people/me",
                personFields="names,emailAddresses,phoneNumbers",
                pageSize=1000,
                pageToken=page_token,
                sortOrder="FIRST_NAME_ASCENDING",
            )
        )
        # Apply partial response
        request.uri += ("&fields=" + fields_mask)

        results = _execute_with_retry(request)
        all_connections.extend(results.get("connections", []))

        page_token = results.get("nextPageToken")
        if not page_token:
            break

    return all_connections


contacts_router = APIRouter()

@contacts_router.get("/google/contacts")
async def get_contacts(user_id: str):
    try:
        contacts = fetch_contacts(user_id)
        resolved, needs_email = resolve_contacts(contacts)
        #print("resolved: ", resolved)
        merged = merge_contacts(resolved)
        #print("merged: ", merged)
        by_name = contacts_name_map(merged)            # name -> {email, phone}
        #print("by_name: ", by_name)
        save_contacts_to_runtime(user_id, by_name)
        return {"contacts": by_name}
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import asyncio
    contacts = asyncio.run(get_contacts("972546610653"))
    print("contacts: ", contacts)