import re
from skills.base_skill import BaseSkill
from core.config import config
from services.ragas_service import ragas_service
from core.logger import logger

class RagaSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "Raga Query Skill"

    @property
    def description(self) -> str:
        return "Looks up ragas, their arohana/avarohana scales, categories, and traditions."
    @staticmethod
    def has_raga_intent_static(transcription: str, engine=None) -> bool:
        cmd = transcription.lower().strip()
        
        # 1. Explicitly namespaced
        if "in music space" in cmd:
            return True
            
        # 2. Strict music keywords always trigger raga intent
        strict_music_keywords = ["arohana", "avarohana", "raga", "melakarta", "janya"]
        if any(kw in cmd for kw in strict_music_keywords):
            return True
            
        # 3. If in music space, allow general queries, EXCEPT system/lifecycle/other skills
        if engine and getattr(engine, "current_space", None) == "music":
            system_patterns = [
                r"\b(shutdown|shut\s+down|exit|quit|go\s+passive|sleep|cancel|stop)\b",
                r"\b(volume|mute|unmute|brightness|lock\s+computer|lock\s+screen)\b",
                r"\b(chrome|notepad|vs\s*code|take\s+a?\s*screenshot|screen\s+shot)\b",
                r"\b(date|time|weather|calculator|contacts|call)\b",
                r"^open\s+(?!raga\b)\w+",
                r"^launch\s+(?!raga\b)\w+",
                r"^start\s+(?!raga\b)\w+"
            ]
            if any(re.search(pat, cmd) for pat in system_patterns):
                return False
            return True
            
        # 4. Outside music space, if no strict keywords, check for "scale"
        if "scale" in cmd and not any(x in cmd for x in ["weight", "fish", "map"]):
            return True
            
        return False

    @staticmethod
    def extract_raga_target_static(transcription: str) -> str:
        cmd = transcription.lower().strip()
        if cmd.startswith("in music space"):
            cmd = re.sub(r"^in music space\s*,?\s*", "", cmd, flags=re.IGNORECASE).strip()
        target = cmd
        target = re.sub(r"\b(tell me about|look up|show me|search for|what is|whats the|what's the)\b", "", target).strip()
        target = re.sub(r"\braga\b", "", target).strip()
        if "arohana of" in cmd or "arohanam of" in cmd:
            target = re.sub(r".*?\barohanam?\s+of\b", "", cmd).strip()
        elif "avarohana of" in cmd or "avarohanam of" in cmd:
            target = re.sub(r".*?\bavarohanam?\s+of\b", "", cmd).strip()
        elif "scale of" in cmd:
            target = re.sub(r".*?\bscale\s+of\b", "", cmd).strip()
        target = re.sub(r"[.,!?;:'\"]+", "", target).strip()
        return target
    def matches(self, command: str, engine=None) -> bool:
        cmd = command.lower().strip()
        cmd = re.sub(r"^jarvis\s*,?\s*", "", cmd).strip()
        
        # Explicitly namespaced
        if cmd.startswith("in music space"):
            return True
            
        # Inside Music Space context
        if engine and getattr(engine, "current_space", None) == "music":
            # Keyword triggers
            music_keywords = ["arohana", "avarohana", "raga", "scale", "melakarta", "janya"]
            if any(kw in cmd for kw in music_keywords):
                return True
            
            # Direct name matching check
            # We strip common helper words to see if the remainder matches a raga
            clean_cmd = re.sub(r"\b(what is|tell me about|look up|show me|search for)\b", "", cmd).strip()
            res = ragas_service.resolve_raga(clean_cmd)
            if res["status"] != "no_match":
                return True

        return False

    def execute(self, command: str, engine=None) -> str:
        cmd = command.lower().strip()
        cmd = re.sub(r"^jarvis\s*,?\s*", "", cmd).strip()
        salutation = config.salutation
        
        # Strip explicit namespace
        if cmd.startswith("in music space"):
            cmd = re.sub(r"^in music space\s*,?\s*", "", cmd, flags=re.IGNORECASE).strip()
            
        # Parse aspects and raga target name
        aspect = "all"
        target = cmd
        
        # Clean common prefixes
        target = re.sub(r"\b(tell me about|look up|show me|search for|what is|whats the|what's the)\b", "", target).strip()
        target = re.sub(r"\braga\b", "", target).strip()
        
        # Check aspect triggers
        if "arohana of" in cmd or "arohanam of" in cmd:
            aspect = "arohana"
            target = re.sub(r".*?\barohanam?\s+of\b", "", cmd).strip()
        elif "avarohana of" in cmd or "avarohanam of" in cmd:
            aspect = "avarohana"
            target = re.sub(r".*?\bavarohanam?\s+of\b", "", cmd).strip()
        elif "scale of" in cmd:
            aspect = "scale"
            target = re.sub(r".*?\bscale\s+of\b", "", cmd).strip()

        # Clean punctuation from target
        target = re.sub(r"[.,!?;:'\"]+", "", target).strip()
        
        if not target:
            return f"Which raga would you like to query, {salutation}?"

        res = ragas_service.resolve_raga(target)
        if res["status"] == "no_match":
            return f"I could not find any raga matching '{target}' in the database, {salutation}."
            
        elif res["status"] == "resolved":
            raga = res["raga"]
            name = raga["name"]
            aroh = ", ".join(raga["arohana"])
            avah = ", ".join(raga["avarohana"])
            cat = raga["category"]
            
            # Sync with Music Space HUD
            try:
                from services.music_space_controller import music_space_controller
                music_space_controller.set_raga(name, cat, raga["arohana"])
            except Exception as e:
                logger.error(f"Failed to update music space raga state: {e}")
            
            if aspect == "arohana":
                return f"The arohana of raga {name} is: {aroh}, {salutation}."
            elif aspect == "avarohana":
                return f"The avarohana of raga {name} is: {avah}, {salutation}."
            elif aspect == "scale":
                return f"Raga {name} has Arohana: {aroh}. Avarohana: {avah}, {salutation}."
            else:
                parent_info = ""
                if raga.get("parent_id"):
                    # Fetch parent name
                    with raga_db_conn() as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT name FROM ragas WHERE id = ?", (raga["parent_id"],))
                        p_row = cursor.fetchone()
                        if p_row:
                            parent_info = f" derived from parent {p_row[0]}"
                
                return f"Raga {name} is a {cat}{parent_info} of the {raga['tradition']} tradition. Arohana: {aroh}. Avarohana: {avah}, {salutation}."
                
        elif res["status"] == "ambiguous":
            candidates = res["candidates"]
            
            # Save candidates in engine if available
            if engine:
                engine.pending_raga_candidates = candidates
                engine.pending_command_aspect = aspect
                engine.consecutive_invalid = 0
                engine.transition_to("SESSION_LISTENING")
                engine._reset_session_timer()
                
            # Build list
            options = []
            for idx, c in enumerate(candidates, 1):
                options.append(f"{idx}. {c['name']}")
            options_str = " or ".join(options)
            
            return f"I found multiple ragas matching '{target}': {options_str}. Please say the number of the one you mean."

        return f"Sorry {salutation}, I couldn't process that query."

def raga_db_conn():
    from core.database import db
    return db.get_connection()
