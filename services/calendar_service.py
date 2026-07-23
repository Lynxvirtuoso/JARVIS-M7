import os
import re
import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from core.logger import logger

# Google Calendar and People API Scopes
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/contacts.readonly'
]

def get_local_timezone_name() -> str:
    """
    Detects local timezone and returns IANA timezone string (defaulting to Asia/Kolkata).
    """
    try:
        now = datetime.datetime.now()
        local_tz = now.astimezone().tzinfo
        tz_name = local_tz.tzname(None) if local_tz else ""
        if "India" in tz_name or "IST" in tz_name:
            return "Asia/Kolkata"
        
        windows_to_iana = {
            "India Standard Time": "Asia/Kolkata",
            "IST": "Asia/Kolkata",
            "W. Europe Standard Time": "Europe/Berlin",
            "GMT Standard Time": "Europe/London",
            "Eastern Standard Time": "America/New_York",
            "Central Standard Time": "America/Chicago",
            "Mountain Standard Time": "America/Denver",
            "Pacific Standard Time": "America/Los_Angeles",
        }
        return windows_to_iana.get(tz_name, "Asia/Kolkata")
    except Exception as e:
        logger.warning(f"Failed to detect system timezone, defaulting to Asia/Kolkata. Error: {e}")
        return "Asia/Kolkata"

def get_local_tzinfo():
    """
    Returns the system's timezone tzinfo object.
    """
    return datetime.datetime.now().astimezone().tzinfo

def format_datetime_human(time_info: dict | str) -> str:
    """
    Formats a Google Calendar event time dict or ISO datetime string into a human-readable format.
    Example: "Saturday, July 12 at 2:00 PM"
    """
    if not time_info:
        return "Unknown Time"
    
    if isinstance(time_info, dict):
        if "dateTime" in time_info:
            dt_str = time_info["dateTime"]
        elif "date" in time_info:
            dt_str = time_info["date"]
            try:
                dt = datetime.date.fromisoformat(dt_str)
                return dt.strftime("%A, %B %d (All day)")
            except Exception:
                return dt_str
        else:
            return "Unknown Time"
    else:
        dt_str = time_info

    try:
        dt = datetime.datetime.fromisoformat(dt_str)
        local_tz = get_local_tzinfo()
        if dt.tzinfo:
            dt = dt.astimezone(local_tz)
        else:
            dt = dt.replace(tzinfo=local_tz)

        time_part = dt.strftime("%I:%M %p")
        if time_part.startswith("0"):
            time_part = time_part[1:]
        return dt.strftime(f"%A, %B %d at {time_part}")
    except Exception as e:
        logger.error(f"Error formatting datetime: {e}")
        return dt_str

def _ensure_rfc3339(dt_str: str) -> str:
    if not dt_str:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=get_local_tzinfo())
        return parsed.isoformat()
    except Exception as e:
        logger.error(f"Error converting datetime string '{dt_str}' to RFC3339: {e}")
        return dt_str

class CalendarService:
    def __init__(self, credentials_path: str = "credentials.json", token_path: str = "token.json"):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.creds = None
        self.service = None

    def authenticate(self) -> Credentials:
        """
        Authenticates/loads stored credentials or runs the OAuth flow if expired/missing.
        """
        if os.path.exists(self.token_path):
            try:
                self.creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
            except Exception as e:
                logger.error(f"Error reading token.json: {e}")

        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                    logger.info("Credentials refreshed successfully.")
                except Exception as e:
                    logger.error(f"Error refreshing credentials: {e}")
                    self.creds = None

            if not self.creds:
                if not os.path.exists(self.credentials_path):
                    raise FileNotFoundError(f"Google OAuth credentials file not found at {self.credentials_path}")
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                self.creds = flow.run_local_server(port=0)
            
            with open(self.token_path, 'w') as token:
                token.write(self.creds.to_json())
                logger.info(f"Token saved successfully to {self.token_path}")

        self.service = build('calendar', 'v3', credentials=self.creds)
        return self.creds

    def get_service(self):
        if not self.service:
            self.authenticate()
        return self.service

    def get_current_time_iso(self) -> str:
        """
        Gets current system time in ISO format with correct timezone offset.
        """
        now = datetime.datetime.now(get_local_tzinfo())
        return now.isoformat()

    def list_events(self, time_min: str = None, time_max: str = None, max_results: int = 50) -> list[dict]:
        """
        Lists events from primary calendar.
        """
        service = self.get_service()
        if not time_min:
            now = datetime.datetime.now(get_local_tzinfo())
            today_start = datetime.datetime(now.year, now.month, now.day, tzinfo=now.tzinfo)
            time_min = today_start.isoformat()

        time_min = _ensure_rfc3339(time_min)
        time_max = _ensure_rfc3339(time_max)

        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        return events_result.get('items', [])

    def resolve_event(self, event_ref: str, time_min: str = None, time_max: str = None) -> dict:
        """
        Resolves a search reference (substring of summary/title) to a single event.
        - Exact matches (case-insensitive summary) are preferred.
        - Substring matches are returned if no exact match.
        - Returns a dictionary detailing status: "resolved", "no_match", or "ambiguous".
        """
        local_tz = get_local_tzinfo()
        now = datetime.datetime.now(local_tz)
        if not time_min:
            time_min = (now - datetime.timedelta(days=7)).isoformat()
        if not time_max:
            time_max = (now + datetime.timedelta(days=60)).isoformat()

        time_min = _ensure_rfc3339(time_min)
        time_max = _ensure_rfc3339(time_max)

        events = self.list_events(time_min=time_min, time_max=time_max, max_results=100)
        
        target = event_ref.strip().lower()
        # Strip common date/time descriptor prefixes that NLU may include in event_ref
        # but which are never part of the actual event summary text.
        # e.g. "today's meeting with Surya" -> "meeting with Surya"
        descriptor_pattern = re.compile(
            r"^\s*(today'?s?\s*|tomorrow'?s?\s*|yesterday'?s?\s*|this\s+|that\s+|next\s+|the\s+)",
            re.IGNORECASE
        )
        cleaned_target = descriptor_pattern.sub("", target).strip()
        if cleaned_target and cleaned_target != target:
            logger.info(f"resolve_event: stripped descriptors from event_ref '{event_ref}' -> '{cleaned_target}'")
            target = cleaned_target
        
        exact_matches = [e for e in events if e.get("summary", "").strip().lower() == target]
        if len(exact_matches) == 1:
            return {"status": "resolved", "event": exact_matches[0]}
        if len(exact_matches) > 1:
            return {"status": "ambiguous", "candidates": exact_matches}

        # Tier 2: token-overlap scoring.
        # Score = (number of target tokens found in the event summary) / len(target_tokens).
        # "meeting with surya" vs "meeting with shakti": only the name token differs,
        # giving the correct event a strictly higher score than any false partial match.
        target_tokens = set(target.split())
        if target_tokens:
            def _token_score(event_summary: str) -> float:
                summary_tokens = set(event_summary.strip().lower().split())
                overlap = target_tokens & summary_tokens
                return len(overlap) / len(target_tokens)

            scored = [
                (e, _token_score(e.get("summary", "")))
                for e in events
                if _token_score(e.get("summary", "")) > 0
            ]
            if scored:
                best_score = max(s for _, s in scored)
                best_candidates = [e for e, s in scored if s == best_score]
                if len(best_candidates) == 1:
                    logger.info(
                        f"resolve_event: token-overlap matched '{best_candidates[0].get('summary')}' "
                        f"(score={best_score:.2f}) for ref '{target}'"
                    )
                    return {"status": "resolved", "event": best_candidates[0]}
                # Multiple candidates with identical best score — still ambiguous
                return {"status": "ambiguous", "candidates": best_candidates}

        # Tier 3: plain substring fallback (for very short / single-word refs)
        substring_matches = [e for e in events if target in e.get("summary", "").lower()]
        if len(substring_matches) == 1:
            return {"status": "resolved", "event": substring_matches[0]}
        elif len(substring_matches) == 0:
            return {"status": "no_match"}
        else:
            return {"status": "ambiguous", "candidates": substring_matches}

    def create_event(self, summary: str, start_time: str, end_time: str, description: str = None, location: str = None) -> dict:
        """
        Creates a new event in the primary calendar.
        """
        service = self.get_service()
        timezone = get_local_timezone_name()
        
        start_time = _ensure_rfc3339(start_time)
        end_time = _ensure_rfc3339(end_time)

        # Check for past date
        dt_start = datetime.datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        now = datetime.datetime.now(dt_start.tzinfo) if dt_start.tzinfo else datetime.datetime.now()
        if dt_start < now - datetime.timedelta(minutes=5):
            raise ValueError("Cannot create calendar events in the past.")

        event_body = {
            'summary': summary,
            'start': {
                'dateTime': start_time,
                'timeZone': timezone,
            },
            'end': {
                'dateTime': end_time,
                'timeZone': timezone,
            }
        }
        if description:
            event_body['description'] = description
        if location:
            event_body['location'] = location

        logger.info(f"Creating event: {summary} starting {start_time}")
        event = service.events().insert(calendarId='primary', body=event_body).execute()
        return event

    def update_event(self, event_id: str, updates: dict) -> dict:
        """
        Updates an existing event.
        """
        service = self.get_service()
        event = service.events().get(calendarId='primary', eventId=event_id).execute()
        
        timezone = get_local_timezone_name()
        
        if 'start_time' in updates and 'end_time' not in updates:
            try:
                orig_start_str = event.get('start', {}).get('dateTime') or event.get('start', {}).get('date')
                orig_end_str = event.get('end', {}).get('dateTime') or event.get('end', {}).get('date')
                if orig_start_str and orig_end_str:
                    from datetime import datetime
                    dt_start = datetime.fromisoformat(orig_start_str.replace("Z", "+00:00"))
                    dt_end = datetime.fromisoformat(orig_end_str.replace("Z", "+00:00"))
                    duration = dt_end - dt_start
                    new_start_dt = datetime.fromisoformat(_ensure_rfc3339(updates['start_time']).replace("Z", "+00:00"))
                    new_end_dt = new_start_dt + duration
                    updates['end_time'] = new_end_dt.isoformat()
            except Exception as e:
                logger.error(f"Failed to auto-adjust end_time: {e}")

        for key, value in updates.items():
            if key == 'start_time':
                event['start'] = {
                    'dateTime': _ensure_rfc3339(value),
                    'timeZone': timezone
                }
            elif key == 'end_time':
                event['end'] = {
                    'dateTime': _ensure_rfc3339(value),
                    'timeZone': timezone
                }
            elif key in ('start', 'end') and isinstance(value, dict) and 'dateTime' in value:
                event[key] = {
                    'dateTime': _ensure_rfc3339(value['dateTime']),
                    'timeZone': timezone
                }
            else:
                event[key] = value

        logger.info(f"Updating event {event_id}: {updates}")
        updated_event = service.events().update(calendarId='primary', eventId=event_id, body=event).execute()
        return updated_event

    def delete_event(self, event_id: str):
        """
        Deletes an event from primary calendar.
        """
        service = self.get_service()
        logger.info(f"Deleting event {event_id}")
        service.events().delete(calendarId='primary', eventId=event_id).execute()

# Global service instance
calendar_service = CalendarService()
