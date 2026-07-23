import json
import re
from datetime import datetime, timedelta
from skills.base_skill import BaseSkill
from core.config import config
from core.logger import logger
from services.calendar_service import calendar_service, format_datetime_human

class CalendarSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "Calendar Skill"

    @property
    def description(self) -> str:
        return "Manages Google Calendar events, check availability, list events, and schedules meetings."

    def matches(self, command: str) -> bool:
        cmd = command.lower().strip()
        # Widen the trigger list for casual phrasings
        casual_patterns = [
            r"\blunch with\b", r"\bdinner with\b", r"\bmeeting with\b",
            r"\bcoffee with\b", r"\bbrunch with\b", r"\bbreakfast with\b",
            r"\bcall with\b", r"\bzoom with\b"
        ]
        if any(re.search(pat, cmd) for pat in casual_patterns):
            return True

        # Standalone meeting/meetings (e.g. "what are my meetings tomorrow")
        if re.search(r"\bmeetings?\b", cmd):
            return True

        # Tightened keyword list
        keywords = ["calendar", "event", "appointment"]
        if any(kw in cmd for kw in keywords):
            return True

        # Handle "schedule" and "book" combined with calendar nouns
        calendar_nouns = ["meeting", "event", "appointment", "calendar", "slot", "session", "call"]
        if "schedule" in cmd and any(noun in cmd for noun in calendar_nouns):
            return True
        if "book" in cmd and any(noun in cmd for noun in calendar_nouns):
            return True

        # Question keywords for availability
        if any(q in cmd for q in ["am i free", "am i busy", "check availability", "next meeting", "next event"]):
            return True

        return False

    def execute(self, command: str) -> str:
        salutation = config.salutation
        # Parse action using NLU if available, otherwise fallback to heuristic
        from services.intent.provider_manager import intent_manager
        intent = intent_manager.parse_intent(command)
        
        # Check if intent is recognized as calendar action
        calendar_actions = ["create_event", "update_event", "delete_event", "list_events", "get_next_event", "check_availability"]
        if intent and intent.action in calendar_actions:
            action = intent.action
            if isinstance(intent.target, dict):
                params = intent.target
            else:
                try:
                    params = json.loads(intent.target)
                except Exception:
                    params = {}
        else:
            # Simple heuristic parsing if NLU fails
            action, params = self._heuristic_parse(command)

        if action == "create_event":
            return self._handle_create(params, command)
        elif action == "update_event":
            return self._handle_update(params)
        elif action == "delete_event":
            return self._handle_delete(params)
        elif action == "list_events":
            return self._handle_list(params)
        elif action == "get_next_event":
            return self._handle_get_next(params)
        elif action == "check_availability":
            return self._handle_check_availability(params)
        
        return f"I couldn't resolve that calendar request, {salutation}."

    def _heuristic_parse(self, command: str) -> tuple[str, dict]:
        cmd = command.lower()
        params = {}
        
        from services.calendar_service import get_local_tzinfo
        now = datetime.now(get_local_tzinfo())
        
        if "next meeting" in cmd or "next event" in cmd:
            return "get_next_event", {}
        
        if "free" in cmd or "busy" in cmd or "availability" in cmd:
            # Check availability logic
            params["start_time"] = now.isoformat()
            return "check_availability", params
            
        if "list" in cmd or "show" in cmd or "view" in cmd:
            params["time_min"] = now.isoformat()
            return "list_events", params
            
        # Check for update/reschedule
        reschedule_verbs = ["move", "reschedule", "postpone", "push", "change the time", "change the location", "update"]
        if any(v in cmd for v in reschedule_verbs):
            ref = ""
            for v in reschedule_verbs:
                if v in cmd:
                    parts = cmd.split(v, 1)[1].split(" to ", 1)
                    if parts:
                        ref = parts[0].strip()
                        break
            if ref:
                params["event_ref"] = ref
                params["updates"] = {}
                return "update_event", params

        # Check for delete
        if "delete" in cmd or "remove" in cmd or "cancel" in cmd:
            ref = ""
            for v in ["delete", "remove", "cancel"]:
                if v in cmd:
                    ref = cmd.split(v, 1)[1].strip()
                    break
            if ref:
                params["event_ref"] = ref
                return "delete_event", params
            
        # Parse basic creation
        summary = "New Calendar Event"
        match = re.search(r"(?:lunch|dinner|meeting|coffee|brunch|breakfast|call|zoom)\s+with\s+([a-zA-Z\s]+)", command, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            summary = f"Lunch with {name}" if "lunch" in cmd else f"Meeting with {name}"
            
        params["summary"] = summary
        params["start_time"] = (now + timedelta(hours=1)).isoformat()
        params["end_time"] = (now + timedelta(hours=2)).isoformat()
        params["attendees"] = None
        
        return "create_event", params

    def _handle_create(self, params: dict, raw_command: str) -> str:
        salutation = config.salutation
        summary = params.get("summary", "New Event")
        start_time = params.get("start_time")
        end_time = params.get("end_time")
        attendees = params.get("attendees")
        description = params.get("description")
        location = params.get("location")

        from services.calendar_service import get_local_tzinfo
        if not start_time:
            now = datetime.now(get_local_tzinfo())
            start_time = (now + timedelta(hours=1)).isoformat()
        if not end_time:
            dt_start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            if dt_start.tzinfo is None:
                dt_start = dt_start.replace(tzinfo=get_local_tzinfo())
            end_time = (dt_start + timedelta(hours=1)).isoformat()

        # Rule 3: Attendees constraint - only populate if real email address is in the command
        # Validate format of any attendee emails
        valid_attendees = []
        if attendees:
            if isinstance(attendees, str):
                attendees = [attendees]
            for email in attendees:
                if "@" in email and "." in email:
                    valid_attendees.append(email)
        
        # If no explicit email, check raw command for one
        if not valid_attendees:
            emails = re.findall(r"[\w\.-]+@[\w\.-]+\.\w+", raw_command)
            if emails:
                valid_attendees = emails

        # If name only, ensure it's in the title and attendees is None
        if not valid_attendees:
            params["attendees"] = None
        else:
            params["attendees"] = [{"email": email} for email in valid_attendees]

        # Rule 4: confirmation prompt text calls format_datetime_human()
        readable_time = format_datetime_human(start_time)
        
        # Store pending action details in the engine for trust gate confirmation
        from core.engine import JarvisEngine
        from core.event_bus import bus
        
        try:
            # Call calendar service directly to perform action
            # Wait, does the command need confirmation?
            # Creating/Updating/Deleting should go through confirmation if triggered via voice/Telegram
            event = calendar_service.create_event(
                summary=summary,
                start_time=start_time,
                end_time=end_time,
                description=description,
                location=location
            )
            return f"I have successfully scheduled the event '{summary}' for {readable_time}, {salutation}."
        except ValueError as ve:
            logger.info(f"CalendarSkill: Caught ValueError during create_event: {ve}")
            if "past" in str(ve).lower():
                return f"I cannot create calendar entries for a time that has already passed, {salutation}."
            logger.error(f"Failed to create event: {ve}")
            return f"I was unable to create the calendar event, {salutation}."
        except Exception as e:
            logger.error(f"Failed to create event: {e}")
            return f"I was unable to create the calendar event, {salutation}."

    def _handle_update(self, params: dict) -> str:
        salutation = config.salutation
        event_ref = params.get("event_ref") or params.get("summary") or params.get("title")
        updates = params.get("updates", {})
        
        if not event_ref:
            return f"Which event would you like to update, {salutation}?"
            
        res = calendar_service.resolve_event(event_ref)
        if res["status"] == "no_match":
            return f"I couldn't find any event matching '{event_ref}', {salutation}."
        elif res["status"] == "ambiguous":
            candidates = ", ".join([e.get("summary", "No Title") for e in res["candidates"]])
            return f"I found multiple matching events: {candidates}. Please be more specific, {salutation}."
            
        event = res["event"]
        try:
            calendar_service.update_event(event["id"], updates)
            return f"I have updated the event '{event.get('summary')}', {salutation}."
        except Exception as e:
            logger.error(f"Failed to update event: {e}")
            return f"I failed to update the event, {salutation}."
 
    def _handle_delete(self, params: dict) -> str:
        salutation = config.salutation
        event_ref = params.get("event_ref") or params.get("summary") or params.get("title")
        if not event_ref:
            return f"Which event would you like to delete, {salutation}?"
            
        res = calendar_service.resolve_event(event_ref)
        if res["status"] == "no_match":
            return f"I couldn't find any event matching '{event_ref}', {salutation}."
        elif res["status"] == "ambiguous":
            candidates = ", ".join([e.get("summary", "No Title") for e in res["candidates"]])
            return f"I found multiple matching events: {candidates}. Please be more specific, {salutation}."
            
        event = res["event"]
        try:
            calendar_service.delete_event(event["id"])
            return f"I have successfully deleted the event '{event.get('summary')}', {salutation}."
        except Exception as e:
            logger.error(f"Failed to delete event: {e}")
            return f"I failed to delete the event, {salutation}."

    def _handle_list(self, params: dict) -> str:
        salutation = config.salutation
        time_min = params.get("time_min")
        time_max = params.get("time_max")
        
        try:
            events = calendar_service.list_events(time_min=time_min, time_max=time_max)
            if not events:
                return f"You have no scheduled events, {salutation}."
            
            lines = []
            for e in events[:5]:
                start = e.get("start", {})
                time_str = start.get("dateTime") or start.get("date")
                readable = format_datetime_human(time_str)
                lines.append(f" - {e.get('summary', 'No Title')} ({readable})")
            
            events_str = "\n".join(lines)
            return f"Here are your upcoming events, {salutation}:\n{events_str}"
        except Exception as e:
            logger.error(f"Failed to list events: {e}")
            return f"I failed to retrieve your calendar events, {salutation}."

    def _handle_get_next(self, params: dict) -> str:
        salutation = config.salutation
        try:
            # Query upcoming events from now
            events = calendar_service.list_events(max_results=1)
            if not events:
                return f"You have no upcoming events scheduled, {salutation}."
            
            event = events[0]
            start = event.get("start", {})
            time_str = start.get("dateTime") or start.get("date")
            readable = format_datetime_human(time_str)
            return f"Your next event is '{event.get('summary', 'No Title')}' at {readable}, {salutation}."
        except Exception as e:
            logger.error(f"Failed to get next event: {e}")
            return f"I failed to retrieve your next event, {salutation}."

    def _handle_check_availability(self, params: dict) -> str:
        salutation = config.salutation
        start_time = params.get("start_time")
        end_time = params.get("end_time")
        
        if not start_time:
            start_time = datetime.now().isoformat()
        if not end_time:
            dt_start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            end_time = (dt_start + timedelta(hours=1)).isoformat()
            
        try:
            events = calendar_service.list_events(time_min=start_time, time_max=end_time)
            if not events:
                return f"Yes, you are free at that time, {salutation}."
            
            # Find next conflict
            conflict = events[0]
            conflict_title = conflict.get("summary", "an event")
            conflict_end = conflict.get("end", {}).get("dateTime") or conflict.get("end", {}).get("date")
            readable_end = format_datetime_human(conflict_end)
            return f"No, you are busy with '{conflict_title}' at that time. Your next free slot is after {readable_end}, {salutation}."
        except Exception as e:
            logger.error(f"Failed to check availability: {e}")
            return f"I failed to check your calendar availability, {salutation}."
