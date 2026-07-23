import re
from skills.base_skill import BaseSkill
from core.config import config
from core.logger import logger
from services.contacts_service import contacts_service
from core.event_bus import bus

class CallSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "Call Skill"

    @property
    def description(self) -> str:
        return "Resolves contacts and places phone calls via the Android bridge."

    # Static patterns for local deterministic/fuzzy call-intent matching and target extraction
    CALL_PATTERNS = [
        r"^call\s+(?:up\s+)?(.+)$",
        r"^make\s+(?:a|me\s+a)\s+call\s+to\s+(.+)$",
        r"^phone\s+(.+)$",
        r"^dial\s+(.+)$",
        r"^ring\s+(.+)$",
        r"^give\s+(.+?)\s+a\s+call$",
        r"^get\s+(.+?)\s+on\s+the\s+phone$",
        r"^(?:can\s+you|i\s+want\s+to)\s+call\s+(.+)$",
        r"^place\s+a\s+call\s+to\s+(.+)$",
        r"^reach\s+out\s+to\s+(.+?)\s+by\s+phone$",
        r"^connect\s+me\s+to\s+(.+)$",
        r"^try\s+calling\s+(.+)$"
    ]

    @staticmethod
    def has_call_intent_static(command: str) -> bool:
        cmd = command.lower().strip()
        # Remove common punctuation
        cmd = re.sub(r"[.!?]+", "", cmd).strip()
        if cmd in ("refresh my contacts", "refresh contacts"):
            return True
        if re.search(r"\brename\s+contact\b", cmd) or re.search(r"\balias\b", cmd):
            return True
        for pat in CallSkill.CALL_PATTERNS:
            if re.search(pat, cmd):
                return True
        # Direct word boundary fallback
        call_triggers = [r"\bcall\b", r"\bphone\b", r"\bdial\b", r"\bring\b"]
        return any(re.search(pat, cmd) for pat in call_triggers)

    @staticmethod
    def extract_call_target_static(command: str) -> str | None:
        cmd = command.lower().strip()
        cmd = re.sub(r"[.!?]+", "", cmd).strip()
        for pat in CallSkill.CALL_PATTERNS:
            m = re.match(pat, cmd)
            if m:
                # Return target name or number
                return m.group(1).strip()
        # Heuristic fallback
        for word in ["call", "phone", "dial", "ring"]:
            if cmd.startswith(word + " "):
                return cmd[len(word):].strip()
        return None

    def matches(self, command: str) -> bool:
        return CallSkill.has_call_intent_static(command)

    def execute(self, command: str, engine=None) -> str:
        salutation = config.salutation
        cmd = command.lower().strip()
        
        # Handle manual refresh
        if cmd in ("refresh my contacts", "refresh contacts"):
            try:
                count = contacts_service.refresh_contacts()
                return f"I have successfully refreshed your contacts list. Cached {count} contacts, {salutation}."
            except Exception as e:
                logger.error(f"Failed to refresh contacts: {e}", exc_info=True)
                return f"I was unable to refresh your contacts list, {salutation}."

        # Handle contact override/alias command
        rename_match = re.match(r"^rename\s+contact\s+(.+?)\s+to\s+(.+)$", cmd)
        if not rename_match:
            rename_match = re.match(r"^alias\s+(.+?)\s+as\s+(.+)$", cmd)
        if rename_match:
            target_name = rename_match.group(1).strip()
            override_name = rename_match.group(2).strip()
            override_title = override_name.title()
            msg = contacts_service.set_contact_override(target_name, override_title)
            return msg

        # Parse target using deterministic static method
        target = CallSkill.extract_call_target_static(command)
        
        if not target:
            # Fall back to NLU provider if deterministic parsing didn't find target
            from services.intent.provider_manager import intent_manager
            intent = intent_manager.parse_intent(command)
            if intent and intent.action == "place_call":
                target = intent.target

        if not target:
            return f"Who would you like me to call, {salutation}?"
            
        # Resolve contact
        res = contacts_service.resolve_contact(target)
        if res["status"] == "no_match":
            return f"I couldn't find any contact matching '{target}', {salutation}."
        elif res["status"] == "near_miss":
            contact = res["contact"]
            name = contact["name"]
            number = contact["phone"]
            bus.system_stats_updated.emit({"last_contact_match": name})
            target_cmd = f"place_call_confirmed:{number}:{name}"
            
            if engine:
                engine.pending_command = target_cmd
                engine.pending_command_type = "near_miss_call_resolution"
                engine.misheard_command = command
                engine.transition_to("WAITING_FOR_CONFIRMATION")
                
                confirm_phrase = f"Did you mean to call {name}, {salutation}?"
                from services.speech_service import speech
                speech.speak(confirm_phrase)
                
                if getattr(engine, "last_command_source", "") == "telegram":
                    import time
                    engine.pending_telegram_confirm = {
                        "command": target_cmd,
                        "timestamp": time.time(),
                        "chat_id": engine.last_telegram_chat_id,
                        "message_id": None,
                        "type": "near_miss_call_resolution"
                    }
                    engine.pending_command = None
                    engine.pending_command_type = None
                    msg_id = engine.telegram_bot.send_confirmation_keyboard(
                        engine.last_telegram_chat_id, 
                        confirm_phrase
                    )
                    engine.pending_telegram_confirm["message_id"] = msg_id
                    if engine.in_session:
                        engine.transition_to("SESSION_LISTENING")
                    else:
                        engine._return_to_passive()
                return ""
            return f"Did you mean to call {name}, {salutation}?"
        elif res["status"] == "ambiguous":
            if engine:
                engine.pending_call_candidates = res["candidates"]
                engine.pending_command = "WAITING_FOR_INDEX"
                engine.pending_command_type = "ambiguous_call_resolution"
                engine.transition_to("WAITING_FOR_CONFIRMATION")
            candidates_list = [f"{i+1}. {c['name']}" for i, c in enumerate(res["candidates"])]
            candidates_str = " ".join(candidates_list)
            return f"I found these contacts matching '{target}', {salutation}: {candidates_str}. Which one should I call?"
            
        contact = res["contact"]
        name = contact["name"]
        number = contact["phone"]
        bus.system_stats_updated.emit({"last_contact_match": name})
        
        if engine:
            from core.trust_gate import TrustGate, ToolCall
            tool_call = ToolCall(
                tool_name="call_skill",
                action="place_call",
                target=f"{name} ({number})",
                source=getattr(engine, "last_command_source", "voice"),
                confidence=1.0,
                audio_quality=1.0,
                reversible=False,
                destructive=True
            )
            decision = TrustGate.evaluate(tool_call)
            if decision == "CONFIRM":
                target_cmd = f"place_call_confirmed:{number}:{name}"
                engine.pending_command = target_cmd
                engine.pending_command_type = "place_call"
                engine.misheard_command = command
                engine.transition_to("WAITING_FOR_CONFIRMATION")
                
                confirm_phrase = f"Do you want me to call {name} at {number}, {salutation}?"
                from services.speech_service import speech
                speech.speak(confirm_phrase)
                
                # Handle Telegram confirmation keyboard if source is telegram
                if getattr(engine, "last_command_source", "") == "telegram":
                    import time
                    engine.pending_telegram_confirm = {
                        "command": target_cmd,
                        "timestamp": time.time(),
                        "chat_id": engine.last_telegram_chat_id,
                        "message_id": None
                    }
                    engine.pending_command = None
                    engine.pending_command_type = None
                    msg_id = engine.telegram_bot.send_confirmation_keyboard(
                        engine.last_telegram_chat_id, 
                        confirm_phrase
                    )
                    engine.pending_telegram_confirm["message_id"] = msg_id
                    if engine.in_session:
                        engine.transition_to("SESSION_LISTENING")
                    else:
                        engine._return_to_passive()
                return ""
            
        # Record interaction
        contacts_service.record_interaction(name)

        # Dispatch call trigger via local HTTP phone bridge directly if engine context not provided (fallback)
        from services.phone_bridge import trigger_phone_call
        success, err_msg = trigger_phone_call(number)
        if not success:
            return err_msg
            
        return f"Placing call to {name}, {salutation}."
