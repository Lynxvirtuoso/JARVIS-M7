import os
import sys
import time
import subprocess
import traceback

# Ensure correct pathing and working directory
project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(project_dir)
sys.path.append(project_dir)

# Redirect stdout/stderr to startup_errors.log
try:
    os.makedirs(os.path.join(project_dir, "logs"), exist_ok=True)
    startup_log_path = os.path.join(project_dir, "logs", "startup_errors.log")
    startup_log = open(startup_log_path, "a", encoding="utf-8", buffering=1)
    sys.stdout = startup_log
    sys.stderr = startup_log
except Exception:
    pass

# Uncaught exception hook
def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    sys.stderr.write(f"\n[{os.path.basename(__file__)}] Unhandled exception: {exc_type.__name__}: {exc_value}\n")
    traceback.print_tb(exc_traceback, file=sys.stderr)
    sys.stderr.flush()

sys.excepthook = handle_exception

for attempt in range(4):
    try:
        import psutil
        from pynput import keyboard
        break
    except (ImportError, ModuleNotFoundError) as e:
        sys.stderr.write(f"Import failed (attempt {attempt+1}/4), retrying in 5s: {e}\n")
        sys.stderr.flush()
        if attempt == 3:
            raise e
        time.sleep(5)

HEARTBEAT_PATH = os.path.join(project_dir, "logs", "hotkey_listener_heartbeat.log")

def is_jarvis_running() -> bool:
    """Checks if JARVIS is already running by scanning the process list."""
    current_pid = os.getpid()
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['pid'] == current_pid:
                continue
            cmdline = proc.info['cmdline']
            if cmdline:
                cmd_str = " ".join(cmdline).lower()
                if "main.py" in cmd_str and "jarvis m7" in cmd_str:
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return False

def launch_jarvis():
    """Launches JARVIS M7 OS without the --startup flag."""
    interpreter = sys.executable
    if interpreter.lower().endswith("python.exe"):
        pyw_path = interpreter[:-10] + "pythonw.exe"
        if os.path.exists(pyw_path):
            interpreter = pyw_path

    script_path = os.path.join(project_dir, "main.py")
    
    # Launch detaching the new process so it persists independently
    creation_flags = 0
    if sys.platform == "win32":
        # DETACHED_PROCESS (0x00000008) and CREATE_NEW_PROCESS_GROUP (0x00000200)
        creation_flags = 0x00000008 | 0x00000200

    subprocess.Popen(
        [interpreter, script_path],
        cwd=project_dir,
        creationflags=creation_flags
    )

def on_activate():
    """Triggered on Ctrl+Alt+J."""
    try:
        if not is_jarvis_running():
            launch_jarvis()
    except Exception as e:
        sys.stderr.write(f"Failed to launch JARVIS from hotkey: {e}\n")
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()

def main():
    # Setup global hotkey listener
    hotkey = keyboard.GlobalHotKeys({
        '<ctrl>+<alt>+j': on_activate
    })
    hotkey.start()
    
    # Run loop to update heartbeat every 30 seconds
    while True:
        try:
            with open(HEARTBEAT_PATH, "w", encoding="utf-8") as f:
                f.write(f"HEARTBEAT: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        except Exception as e:
            sys.stderr.write(f"Failed to write heartbeat: {e}\n")
            sys.stderr.flush()
        time.sleep(30)

if __name__ == "__main__":
    main()
