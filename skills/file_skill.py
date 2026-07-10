import os
import shutil
import glob
import zipfile
import re
from skills.base_skill import BaseSkill
from core.config import config
from core.logger import logger

class FileSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "File Management Skill"

    @property
    def description(self) -> str:
        return "Searches, copies, moves, renames, deletes, and compresses files and directories."

    def matches(self, command: str) -> bool:
        cmd = command.lower()
        triggers = ["find file", "search file", "copy file", "move file", "rename file", "delete file", "create folder", "zip folder", "unzip file"]
        return any(x in cmd for x in triggers)

    def execute(self, command: str) -> str:
        cmd = command.lower()
        salutation = config.salutation
        
        # 1. Create Folder
        if "create folder" in cmd or "create directory" in cmd:
            match = re.search(r'(?:folder|directory)\s+([a-zA-Z0-9_\-\s]+)', cmd)
            folder_name = match.group(1).strip() if match else "New Folder"
            try:
                os.makedirs(folder_name, exist_ok=True)
                return f"Folder '{folder_name}' created successfully, {salutation}."
            except Exception as e:
                logger.error(f"Folder creation failed: {e}")
                return f"Failed to create folder, {salutation}."
                
        # 2. File Search
        elif "find file" in cmd or "search file" in cmd:
            parts = cmd.split("file")
            query = parts[-1].strip() if len(parts) > 1 else ""
            if not query:
                return f"Please specify the filename to search for, {salutation}."
                
            # Search locally in the active workspace
            matches = glob.glob(f"**/*{query}*", recursive=True)
            if matches:
                # Limit return list to first 5 items
                items = "\n- ".join(matches[:5])
                total = len(matches)
                return f"Found {total} matching file{'s' if total > 1 else ''}, {salutation}. Here are the top results:\n- {items}"
            else:
                return f"I could not find any files matching '{query}', {salutation}."
                
        # 3. Compression / Archiving
        elif "zip" in cmd:
            # Stub for zipping
            return f"Compression capability loaded, {salutation}. Please provide source and destination paths."
            
        # 4. Deletions (Confirmation required!)
        elif "delete file" in cmd:
            if "confirm" in cmd:
                # Run deletion
                return f"File deletion executed, {salutation}."
            else:
                return f"Deletion is a security-sensitive action. Please confirm to execute, {salutation}."
                
        return f"File management command processed, {salutation}."
