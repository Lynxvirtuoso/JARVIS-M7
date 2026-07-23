import os
import importlib
from skills.base_skill import BaseSkill
from core.logger import logger

class SkillManager:
    """Discovers, loads, and manages JARVIS modular skills."""
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = SkillManager()
        return cls._instance

    def __init__(self):
        self.skills = []
        self.load_skills()

    def load_skills(self):
        self.skills = []
        
        # We will manually import/register our native skills to ensure fast startup and zero import errors
        try:
            from skills.system_skill import SystemSkill
            self.register_skill(SystemSkill())
        except Exception as e:
            logger.error(f"Failed to load SystemSkill: {e}")
            
        try:
            from skills.browser_skill import BrowserSkill
            self.register_skill(BrowserSkill())
        except Exception as e:
            logger.error(f"Failed to load BrowserSkill: {e}")
            
        try:
            from skills.media_skill import MediaSkill
            self.register_skill(MediaSkill())
        except Exception as e:
            logger.error(f"Failed to load MediaSkill: {e}")
            
        try:
            from skills.file_skill import FileSkill
            self.register_skill(FileSkill())
        except Exception as e:
            logger.error(f"Failed to load FileSkill: {e}")
            
        try:
            from skills.productivity_skill import ProductivitySkill
            self.register_skill(ProductivitySkill())
        except Exception as e:
            logger.error(f"Failed to load ProductivitySkill: {e}")

        try:
            from skills.home_assistant_skill import HomeAssistantSkill
            self.register_skill(HomeAssistantSkill())
        except Exception as e:
            logger.error(f"Failed to load HomeAssistantSkill: {e}")

        try:
            from skills.routines_skill import RoutinesSkill
            self.register_skill(RoutinesSkill())
        except Exception as e:
            logger.error(f"Failed to load RoutinesSkill: {e}")

        try:
            from skills.calendar_skill import CalendarSkill
            self.register_skill(CalendarSkill())
        except Exception as e:
            logger.error(f"Failed to load CalendarSkill: {e}")

        try:
            from skills.call_skill import CallSkill
            self.register_skill(CallSkill())
        except Exception as e:
            logger.error(f"Failed to load CallSkill: {e}")

        try:
            from skills.raga_skill import RagaSkill
            self.register_skill(RagaSkill())
        except Exception as e:
            logger.error(f"Failed to load RagaSkill: {e}")

        logger.info(f"Loaded {len(self.skills)} JARVIS system control skills.")

    def register_skill(self, skill: BaseSkill):
        if isinstance(skill, BaseSkill):
            self.skills.append(skill)
            logger.debug(f"Registered skill: {skill.name}")
        else:
            logger.error(f"Attempted to register invalid skill object: {type(skill)}")

    def route_command(self, command: str, engine=None) -> str:
        """
        Scan registered skills to find a match.
        Returns the output text of the executed skill, or None if no skill matches.

        NLU pre-check: if the intent has already been classified as a known action,
        route directly to the corresponding Skill regardless of keyword matching.
        """
        CALENDAR_ACTIONS = {
            "create_event", "update_event", "delete_event",
            "list_events", "get_next_event", "check_availability"
        }
        
        def _exec_with_engine(skill, cmd):
            import inspect
            sig = inspect.signature(skill.execute)
            if 'engine' in sig.parameters:
                return skill.execute(cmd, engine=engine)
            return skill.execute(cmd)

        try:
            from services.intent.provider_manager import intent_manager
            intent = intent_manager.parse_intent(command)
            if intent:
                if intent.action in CALENDAR_ACTIONS:
                    for skill in self.skills:
                        if skill.name == "Calendar Skill":
                            logger.info(
                                f"NLU pre-check: routing '{command}' to Calendar Skill "
                                f"(action={intent.action}, confidence={intent.confidence})"
                            )
                            try:
                                return _exec_with_engine(skill, command)
                            except Exception as e:
                                logger.error(f"Error executing Calendar Skill (NLU pre-check): {e}", exc_info=True)
                                return "I encountered an internal error in the Calendar Skill, Sir."
                elif intent.action == "place_call":
                    for skill in self.skills:
                        if skill.name == "Call Skill":
                            logger.info(
                                f"NLU pre-check: routing '{command}' to Call Skill "
                                f"(action={intent.action}, confidence={intent.confidence})"
                            )
                            try:
                                return _exec_with_engine(skill, command)
                            except Exception as e:
                                logger.error(f"Error executing Call Skill (NLU pre-check): {e}", exc_info=True)
                                return "I encountered an internal error in the Call Skill, Sir."
        except Exception as e:
            logger.warning(f"NLU pre-check in route_command failed, falling back to keyword matching: {e}")

        for skill in self.skills:
            import inspect
            sig = inspect.signature(skill.matches)
            matched = False
            if 'engine' in sig.parameters:
                matched = skill.matches(command, engine=engine)
            else:
                matched = skill.matches(command)
            if matched:
                logger.info(f"Routing command to skill: {skill.name}")
                try:
                    return _exec_with_engine(skill, command)
                except Exception as e:
                    logger.error(f"Error executing skill '{skill.name}': {e}", exc_info=True)
                    return f"I encountered an internal error while executing that task, Sir."
        return None

# Global skill manager
skill_manager = SkillManager.get_instance()
