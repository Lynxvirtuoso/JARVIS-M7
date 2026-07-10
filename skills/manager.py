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

        logger.info(f"Loaded {len(self.skills)} JARVIS system control skills.")

    def register_skill(self, skill: BaseSkill):
        if isinstance(skill, BaseSkill):
            self.skills.append(skill)
            logger.debug(f"Registered skill: {skill.name}")
        else:
            logger.error(f"Attempted to register invalid skill object: {type(skill)}")

    def route_command(self, command: str) -> str:
        """
        Scan registered skills to find a match.
        Returns the output text of the executed skill, or None if no skill matches.
        """
        for skill in self.skills:
            if skill.matches(command):
                logger.info(f"Routing command to skill: {skill.name}")
                try:
                    return skill.execute(command)
                except Exception as e:
                    logger.error(f"Error executing skill '{skill.name}': {e}", exc_info=True)
                    return f"I encountered an internal error while executing that task, Sir."
        return None

# Global skill manager
skill_manager = SkillManager.get_instance()
