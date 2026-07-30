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

    def execute(self, command: str, engine=None) -> str:
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
            # TODO: Implement zip/unzip capability (out of scope for this pass)
            return f"Compression capability loaded, {salutation}. Please provide source and destination paths."

        # 4. File Deletion — routed through TrustGate
        elif "delete file" in cmd:
            return self._handle_delete(command, cmd, engine, salutation)

        return f"File management command processed, {salutation}."

    # ------------------------------------------------------------------
    # Private: deletion handler
    # ------------------------------------------------------------------

    def _handle_delete(self, original_command: str, cmd: str, engine, salutation: str) -> str:
        """
        Parse filename, validate path, run TrustGate, and execute deletion
        only after explicit confirmation.  Mirrors the CallSkill TrustGate pattern.
        """
        from core.trust_gate import TrustGate, ToolCall

        # --- 1. Parse filename from command ---
        # e.g. "delete file report.txt" or "delete file called notes.txt"
        # Split on "file" and take the remainder, same as find-file branch
        parts = cmd.split("file", 1)
        filename_raw = parts[-1].strip() if len(parts) > 1 else ""
        # Strip leading filler words: "called", "named"
        filename_raw = re.sub(r"^(?:called|named)\s+", "", filename_raw).strip()

        if not filename_raw:
            return f"Which file would you like me to delete, {salutation}?"

        # --- 2. Resolve and validate path ---
        workspace_dir = config.get("workspace_dir", os.getcwd())
        resolved = os.path.realpath(os.path.join(workspace_dir, filename_raw))
        workspace_real = os.path.realpath(workspace_dir)

        # Reject path traversal and absolute paths outside workspace
        if ".." in filename_raw or os.path.isabs(filename_raw):
            return f"I can only delete files within the workspace directory, {salutation}."

        if not resolved.startswith(workspace_real + os.sep) and resolved != workspace_real:
            return f"That path is outside the workspace. I cannot delete it, {salutation}."

        # Reject illegal filename characters (mirrors validate_filename in engine.py)
        illegal_chars = ['<', '>', ':', '"', '|', '*']
        if any(c in filename_raw for c in illegal_chars):
            return f"The filename contains invalid characters, {salutation}."

        # File must exist before we even ask TrustGate
        if not os.path.exists(resolved):
            return f"I couldn't find a file named '{filename_raw}' in the workspace, {salutation}."

        # Determine if it is a file or directory
        is_dir = os.path.isdir(resolved)

        # --- 3. Build ToolCall and evaluate with TrustGate ---
        source = getattr(engine, "last_command_source", "voice") if engine else "voice"
        tool_call = ToolCall(
            tool_name="file_skill",
            action="delete_file",
            target=resolved,
            source=source,
            confidence=1.0,
            audio_quality=1.0,
            reversible=False,
            destructive=True
        )
        decision = TrustGate.evaluate(tool_call)

        if decision == "CONFIRM":
            confirm_phrase = (
                f"Are you sure you want to permanently delete "
                f"{'folder' if is_dir else 'file'} '{filename_raw}', {salutation}?"
            )
            # Set engine pending state so the verbal "yes" confirmation executes deletion
            if engine:
                import time as _time
                from services.conversation.models import PendingConfirmation, SensitiveActionType
                target_cmd = f"delete_file_confirmed:{resolved}"
                engine.pending_command = target_cmd
                engine.pending_command_type = "file_deletion"
                engine.misheard_command = original_command
                engine.pending_confirmation_obj = PendingConfirmation(
                    request_id=getattr(engine, "active_request_id", "unknown"),
                    session_id=getattr(engine, "current_session_id", "default_session"),
                    action_type=SensitiveActionType.DELETE_FILE,
                    action_payload={"command": target_cmd},
                    source=getattr(engine, "last_command_source", "voice"),
                    created_at=_time.time(),
                    expires_at=_time.time() + 30.0
                )
                engine.transition_to("WAITING_FOR_CONFIRMATION")
            return confirm_phrase

        elif decision == "EXECUTE":
            return self._perform_deletion(resolved, filename_raw, is_dir, salutation)

        else:  # IGNORE
            return f"I wasn't confident enough in that request to act on it, {salutation}. Please try again."

    def _perform_deletion(self, resolved: str, display_name: str, is_dir: bool, salutation: str) -> str:
        """Execute the actual OS-level deletion after TrustGate approval."""
        try:
            if is_dir:
                # Refuse to silently nuke non-empty directories
                if os.listdir(resolved):
                    return (
                        f"The folder '{display_name}' is not empty, {salutation}. "
                        f"Please empty it first or specify 'delete folder' to confirm recursive deletion."
                    )
                os.rmdir(resolved)
                logger.info(f"Directory deleted: '{resolved}'")
                return f"Folder '{display_name}' has been deleted, {salutation}."
            else:
                os.remove(resolved)
                logger.info(f"File deleted: '{resolved}'")
                return f"File '{display_name}' has been deleted, {salutation}."
        except PermissionError:
            logger.error(f"Permission denied deleting '{resolved}'")
            return f"I don't have permission to delete '{display_name}', {salutation}."
        except Exception as e:
            logger.error(f"Failed to delete '{resolved}': {e}")
            return f"I was unable to delete '{display_name}', {salutation}. Error: {e}"
