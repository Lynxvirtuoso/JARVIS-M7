import sys
import os
sys.path.append(r"d:\JARVIS M7")

from core.autostart import (
    get_launch_command,
    is_autostart_enabled,
    enable_autostart,
    disable_autostart,
    reconcile_autostart_config
)
from core.config import config
from core.database import db

def test_autostart_flow():
    print("Testing get_launch_command()...")
    cmd = get_launch_command()
    print("Launch command is:", cmd)
    assert "--startup" in cmd, "Launch command must contain --startup"
    
    # Store initial state to restore later
    initial_reg = is_autostart_enabled()
    initial_config = config.autostart_enabled
    print(f"Initial registry enabled: {initial_reg}")
    print(f"Initial config enabled: {initial_config}")
    
    try:
        print("\n--- Test enable_autostart() ---")
        enable_autostart()
        assert is_autostart_enabled() is True, "Registry should show autostart is enabled"
        print("enable_autostart() succeeded and verified.")
        
        print("\n--- Test disable_autostart() ---")
        disable_autostart()
        assert is_autostart_enabled() is False, "Registry should show autostart is disabled"
        print("disable_autostart() succeeded and verified.")
        
        print("\n--- Test Config Sync via config.set ---")
        config.set("autostart_enabled", True)
        assert is_autostart_enabled() is True, "Registry should be synced to True"
        assert config.autostart_enabled is True, "Config property should return True"
        print("Config set to True synced to registry successfully.")
        
        config.set("autostart_enabled", False)
        assert is_autostart_enabled() is False, "Registry should be synced to False"
        assert config.autostart_enabled is False, "Config property should return False"
        print("Config set to False synced to registry successfully.")
        
        print("\n--- Test reconciliation mismatch ---")
        # Manually enable in registry, but leave config as False
        enable_autostart()
        print("Forcing registry = True, config = False for mismatch check.")
        reconcile_autostart_config()
        assert config.autostart_enabled is True, "Reconciliation should set config to True to match registry"
        print("Reconciliation successfully matched config to registry.")
        
        # Cleanup
        disable_autostart()
        reconcile_autostart_config()
        print("Reconciliation cleanup to False successful.")
        
    finally:
        # Restore initial state
        print("\nRestoring initial state...")
        if initial_reg:
            enable_autostart()
        else:
            disable_autostart()
        db.set_setting("autostart_enabled", initial_config)
        config.json_config["autostart_enabled"] = initial_config
        with open(config.json_path, 'w', encoding='utf-8') as f:
            import json
            json.dump(config.json_config, f, indent=4)
        print("Initial state restored.")

if __name__ == "__main__":
    test_autostart_flow()
