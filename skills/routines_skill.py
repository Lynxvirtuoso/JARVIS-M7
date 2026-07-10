import time
import threading
import re
from skills.base_skill import BaseSkill
from core.event_bus import bus
from core.config import config
from core.logger import logger

class RoutinesSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "Routines Skill"

    @property
    def description(self) -> str:
        return "Executes custom routines or macros combining multiple system and home automation commands."

    def matches(self, command: str) -> bool:
        cmd = command.lower().strip()
        # Clean punctuation
        cmd = re.sub(r"[.,!?;:'\"]+", "", cmd).strip()
        
        # 1. Built-in checks
        if any(x in cmd for x in ["good night", "morning routine", "work routine", "movie mode"]):
            return True
            
        # 2. Listing routines
        if cmd in ["list routines", "what routines do i have", "list routine"]:
            return True
            
        # 3. Deleting routines
        if cmd.startswith("delete routine ") or cmd.startswith("delete the routine "):
            return True
            
        # 4. Executing custom routines
        if cmd.startswith("run ") and cmd.endswith(" routine"):
            return True
        if cmd.startswith("engage ") and cmd.endswith(" mode"):
            return True
            
        return False

    def execute(self, command: str) -> str:
        cmd = command.lower().strip()
        cmd = re.sub(r"[.,!?;:'\"]+", "", cmd).strip()
        salutation = config.salutation
        
        from core.database import db
        
        # Built-in execution
        if "good night" in cmd:
            threading.Thread(target=self._run_good_night, daemon=True).start()
            return f"Initiating good night routine. Sweet dreams, {salutation}."
            
        elif "morning routine" in cmd:
            threading.Thread(target=self._run_morning, daemon=True).start()
            return f"Systems waking up. Good morning, {salutation}."
            
        elif "work routine" in cmd:
            threading.Thread(target=self._run_work, daemon=True).start()
            return f"Activating workstation productivity profile, {salutation}."
            
        elif "movie mode" in cmd:
            threading.Thread(target=self._run_movie_mode, daemon=True).start()
            return f"Activating movie mode, {salutation}."
            
        # Listing routines
        elif cmd in ["list routines", "what routines do i have", "list routine"]:
            routines = db.get_all_routines()
            if not routines:
                return f"You do not have any custom routines configured, {salutation}."
            routines_str = ", ".join(routines)
            return f"Here are your custom routines: {routines_str}, {salutation}."
            
        # Deleting routines
        elif cmd.startswith("delete routine ") or cmd.startswith("delete the routine "):
            if cmd.startswith("delete the routine "):
                name = cmd[len("delete the routine "):].strip()
            else:
                name = cmd[len("delete routine "):].strip()
            
            db.delete_routine(name)
            return f"Routine {name} has been successfully deleted, {salutation}."
            
        # Executing routines
        elif (cmd.startswith("run ") and cmd.endswith(" routine")) or (cmd.startswith("engage ") and cmd.endswith(" mode")):
            if cmd.startswith("run ") and cmd.endswith(" routine"):
                name = cmd[4:-8].strip()
                if not db.get_routine(name):
                    alt_name = cmd[4:].strip()
                    if db.get_routine(alt_name):
                        name = alt_name
            else:
                name = cmd[7:-5].strip()
                if not db.get_routine(name):
                    alt_name = cmd[7:].strip()
                    if db.get_routine(alt_name):
                        name = alt_name
                
            steps = db.get_routine(name)
            if steps:
                threading.Thread(target=self._run_custom_routine, args=(name, steps), daemon=True).start()
                return f"Running routine {name}, {salutation}."
            else:
                return f"I could not find a routine called {name}, {salutation}."
                
        return f"Routine recognized but no steps defined, {salutation}."

    def _run_good_night(self):
        logger.info("Starting Good Night Routine...")
        # Step 1: Mute volume
        bus.command_received.emit("mute volume")
        time.sleep(1.5)
        # Step 2: Turn off lights (Home Assistant fallback)
        bus.command_received.emit("turn off lights")
        time.sleep(1.5)
        # Step 3: Lock PC
        bus.command_received.emit("lock workstation")

    def _run_morning(self):
        logger.info("Starting Morning Routine...")
        # Step 1: Unmute
        bus.command_received.emit("unmute volume")
        time.sleep(1.5)
        # Step 2: Turn on kitchen lights
        bus.command_received.emit("turn on kitchen lights")

    def _run_work(self):
        logger.info("Starting Work Routine...")
        # Step 1: Open VS Code
        bus.command_received.emit("open visual studio code")
        time.sleep(2.0)
        # Step 2: Open GitHub
        bus.command_received.emit("open github.com")

    def _run_movie_mode(self):
        logger.info("Starting Movie Mode Routine...")
        # Step 1: decrease volume
        bus.command_received.emit("decrease volume")
        time.sleep(1.5)
        # Step 2: mute volume
        bus.command_received.emit("mute volume")

    def _run_custom_routine(self, name, steps):
        logger.info(f"Starting custom routine '{name}' with steps: {steps}")
        for step in steps:
            logger.info(f"Routine '{name}' executing step: {step}")
            bus.command_received.emit(step)
            time.sleep(1.5)
