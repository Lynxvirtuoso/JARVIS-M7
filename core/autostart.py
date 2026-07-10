import os
import sys
import winreg
import win32com.client
from core.logger import logger

REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_NAME = "JARVIS M7"
REG_NAME_HOTKEY = "JARVIS Hotkey Listener"

STARTUP_DIR = os.path.join(os.environ["APPDATA"], r"Microsoft\Windows\Start Menu\Programs\Startup")
LNK_JARVIS = os.path.join(STARTUP_DIR, "JARVIS M7.lnk")
LNK_HOTKEY = os.path.join(STARTUP_DIR, "JARVIS Hotkey Listener.lnk")

def clean_old_registry_keys():
    """Cleans up the legacy Registry Run keys if they exist."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_WRITE)
        try:
            for name in (REG_NAME, REG_NAME_HOTKEY):
                try:
                    winreg.DeleteValue(key, name)
                    logger.info(f"Cleaned legacy Registry Run key: {name}")
                except FileNotFoundError:
                    pass
        finally:
            winreg.CloseKey(key)
    except Exception as e:
        logger.debug(f"Could not clean legacy Registry keys: {e}")

def get_interpreter_path() -> str:
    """Gets the path to the pythonw.exe or python.exe interpreter."""
    interpreter = sys.executable
    if interpreter.lower().endswith("python.exe"):
        pyw_path = interpreter[:-10] + "pythonw.exe"
        if os.path.exists(pyw_path):
            interpreter = pyw_path
    return interpreter

TASK_NAME_JARVIS = "JARVIS_M7_Startup_Task"
TASK_NAME_HOTKEY = "JARVIS_M7_Hotkey_Task"

def clean_legacy_shortcuts():
    """Cleans up the legacy Startup folder shortcuts if they exist."""
    for path in (LNK_JARVIS, LNK_HOTKEY):
        try:
            if os.path.exists(path):
                os.remove(path)
                logger.info(f"Cleaned legacy Startup shortcut: {path}")
        except Exception as e:
            logger.debug(f"Could not clean legacy Startup shortcut '{path}': {e}")

def create_scheduled_task(task_name: str, script_relative_path: str, arguments: str = "", delay_str: str = "PT45S"):
    """Creates a Windows Task Scheduler task triggered at logon with a delayed start."""
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        interpreter = get_interpreter_path()
        script_path = os.path.join(base_dir, script_relative_path)
        
        full_args = f'"{script_path}"'
        if arguments:
            full_args += f' {arguments}'

        scheduler = win32com.client.Dispatch("Schedule.Service")
        scheduler.Connect()
        root_folder = scheduler.GetFolder("\\")
        
        # Delete if already exists to ensure fresh settings
        try:
            root_folder.DeleteTask(task_name, 0)
        except Exception:
            pass

        task_def = scheduler.NewTask(0)
        
        # Principal (run in interactive logon token under current user, no elevation needed)
        principal = task_def.Principal
        principal.RunLevel = 0 # 0 = TASK_RUNLEVEL_LUA (Least Privilege)
        
        # Settings
        settings = task_def.Settings
        settings.Enabled = True
        settings.StartWhenAvailable = True
        settings.Hidden = False
        settings.DisallowStartIfOnBatteries = False
        settings.StopIfGoingOnBatteries = False
        settings.AllowHardTerminate = True
        settings.ExecutionTimeLimit = "PT0S" # No limit
        
        # Logon Trigger (9 = TriggerTypeLogon)
        trigger = task_def.Triggers.Create(9)
        trigger.Id = f"{task_name}_LogonTrigger"
        trigger.Delay = delay_str
        
        user = f"{os.environ.get('USERDOMAIN')}\\{os.environ.get('USERNAME')}"
        trigger.UserId = user
        
        # Action (0 = ActionTypeExecute)
        action = task_def.Actions.Create(0)
        action.Path = interpreter
        action.Arguments = full_args
        action.WorkingDirectory = base_dir
        
        # Register the task (6 = TaskCreateOrUpdate, 3 = TASK_LOGON_INTERACTIVE_TOKEN)
        root_folder.RegisterTaskDefinition(
            task_name,
            task_def,
            6, # TASK_CREATE_OR_UPDATE
            user,
            None,
            3 # TASK_LOGON_INTERACTIVE_TOKEN
        )
        logger.info(f"Created scheduled task '{task_name}': {interpreter} {full_args} with delay {delay_str}")
    except Exception as e:
        logger.error(f"Failed to create scheduled task '{task_name}': {e}")
        raise OSError(f"Failed to enable autostart task: {e}") from e

def delete_scheduled_task(task_name: str) -> bool:
    """Deletes a Windows Task Scheduler task."""
    try:
        scheduler = win32com.client.Dispatch("Schedule.Service")
        scheduler.Connect()
        root_folder = scheduler.GetFolder("\\")
        root_folder.DeleteTask(task_name, 0)
        logger.info(f"Deleted scheduled task '{task_name}'")
        return True
    except Exception as e:
        logger.debug(f"Could not delete scheduled task '{task_name}': {e}")
        return False

def is_task_registered(task_name: str) -> bool:
    """Checks if a task is registered in the Windows Task Scheduler."""
    try:
        scheduler = win32com.client.Dispatch("Schedule.Service")
        scheduler.Connect()
        root_folder = scheduler.GetFolder("\\")
        root_folder.GetTask(task_name)
        return True
    except Exception:
        return False

def is_autostart_enabled() -> bool:
    """Checks if the Task Scheduler task for JARVIS exists."""
    return is_task_registered(TASK_NAME_JARVIS)

def is_hotkey_autostart_enabled() -> bool:
    """Checks if the Task Scheduler task for the Hotkey Listener exists."""
    return is_task_registered(TASK_NAME_HOTKEY)

def enable_autostart():
    """Enables autostart by registering Windows Task Scheduler tasks and cleaning legacy keys/shortcuts."""
    clean_old_registry_keys()
    clean_legacy_shortcuts()
    create_scheduled_task(TASK_NAME_JARVIS, "main.py", "--startup", "PT45S")
    create_scheduled_task(TASK_NAME_HOTKEY, os.path.join("launcher", "hotkey_listener.py"), "", "PT45S")

def disable_autostart():
    """Disables autostart by deleting the tasks and cleaning legacy keys/shortcuts."""
    clean_old_registry_keys()
    clean_legacy_shortcuts()
    delete_scheduled_task(TASK_NAME_JARVIS)
    delete_scheduled_task(TASK_NAME_HOTKEY)

def sync_autostart_with_config(enabled: bool):
    """Updates startup state to match the requested configuration setting."""
    if enabled:
        enable_autostart()
    else:
        disable_autostart()

def reconcile_autostart_config():
    """
    On startup, compare the actual shortcut state against config.autostart_enabled.
    Reconciles them by preferring the shortcut state as the source of truth.
    """
    try:
        from core.config import config
        from core.database import db
        import json
        
        reg_enabled = is_autostart_enabled()
        cfg_enabled = config.autostart_enabled
        
        if reg_enabled != cfg_enabled:
            logger.info(f"Reconciling autostart setting: Shortcuts Exist={reg_enabled}, Config={cfg_enabled}. Updating config to match.")
            
            # Update database setting
            db.set_setting("autostart_enabled", reg_enabled)
            
            # Update config.json directly
            config.json_config["autostart_enabled"] = reg_enabled
            try:
                with open(config.json_path, 'w', encoding='utf-8') as f:
                    json.dump(config.json_config, f, indent=4)
            except Exception as e:
                logger.error(f"Failed to write reconciled config to config.json: {e}")
    except Exception as e:
        logger.error(f"Error during autostart reconciliation: {e}")


