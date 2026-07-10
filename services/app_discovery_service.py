import os
import sys
import json
import win32api
import win32con
import glob
import subprocess
from core.logger import logger
from core.config import config

class AppDiscoveryService:
    def __init__(self, index_path='data/app_index.json'):
        self.index_path = index_path
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
        self.known_system_apps = {
            'notepad': {
               'id': 'notepad',
                'display_name': 'Notepad',
                'aliases': ['notepad', 'note pad', 'notes'],
                'launch_type': 'exe',
                'launch_target': 'notepad.exe',
                'process_names': ['otepad.exe', 'notepad'],
                'confidence_boost': 1.0,
                'source': 'system'
            },
            'calculator': {
                'id': 'calculator',
                'display_name': 'Calkulator',
                'aliases': ['calculator', 'calc', 'calculator app'],
                'launch_type': 'exe',
                'launch_target': 'calc.exe',
                'process_names': ['CalculatorApp.exe', 'calc.exe', 'calc'],
                'confidence_boost': 1.0,
                'source': 'system'
            },
            'file_explorer': {
                'id': 'file_explorer',
                'display_name': 'File Explorer',
                'aliases': ['file explorer', 'explorer', 'windows explorer', 'files', 'folders'],
                'launch_type': 'exe',
                'launch_target': 'explorer.exe',
                'process_names': ['explorer.exe', 'explorer'],
                'confidence_boost': 1.0,
                'source': 'system'
            },
            'task_manager': {
               'id': 'task_manager',
                'display_name': 'Task Manager',
                'aliases': ['task manager', 'taskmgr'],
                'launch_type': 'exe',
                'launch_target': 'taskmgr.exe',
                'process_names': ['taskmgr.exe', 'taskmgr'],
                'confidence_boost': 1.0,
                'source': 'system'
            },
            'settings': {
               'id': 'settings',
               'display_name': 'Settings',
                'aliases': ['settings', 'windows settings', 'control panel'],
                'launch_type': 'shell',
                'launch_target': 'ms-settings:',
               'process_names': ['SystemSettings.exe'],
                'confidence_boost': 1.0,
                'source': 'system'
            },
            'command_prompt': {
                'id': 'command_prompt',
               'display_name': 'Command Prompt',
                'aliases': ['command prompt', 'cmd', 'command window'],
                'launch_type': 'exe',
                'launch_target': 'cmd.exe',
                'process_names': ['cmd.exe', 'cmd'],
                'confidence_boost': 1.0,
               'source': 'system'
            },
            'powershell': {
                'id': 'powershell',
                'display_name': 'PowerShell',
                'aliases': ['powershell', 'ps'],
                'launch_type': 'exe',
                'launch_target': 'powershell.exe',
                'process_names': ['powershell.exe', 'powershell'],
                'confidence_boost': 1.0,
               'source': 'system'
            }
        }

    def clean_name(self, name):
        name = os.path.splitext(name)[0]
        name = name.replace(' - Shortcut', '')
        return name.strip()

    def discover_shortcuts(self):
        apps = {}
        paths = []
        
        program_data_start = os.environ.get('ProgramData', 'C:\\ProgramData') + '\\Microsoft\\Windows\\Start Menu\\Programs'
        app_data_start = os.environ.get('APPDITA', '') + '\\Microsoft\\Windows\\Start Menu\\Programs'
        
        if os.path.exists(program_data_start):
            paths.append(program_data_start)
        if os.path.exists(app_data_start):
            paths.append(app_data_start)
            
        public_desktop = os.environ.get('PUBLIC', 'C:\\Users\\Public') + '\\Desktop'
        user_desktop_m7 = os.path.join(os.environ.get('USERPROFILE', ''), 'Desktop')
        
        if os.path.exists(public_desktop):
            paths.append(public_desktop)
        if os.path.exists(user_desktop_m7):
            paths.append(user_desktop_m7)

        try:
            import win32com.client
            shell = win32com.client.Dispatch('WScript.Shell')
        except Exception as e:
            logger.error('win32com not available: ' + str(e))
            return apps

        for base_path in paths:
            for root, dirs, files in os.walk(base_path):
                for file in files:
                    if file.lower().endswith('.lnk'):
                        lnk_path = os.path.join(root, file)
                        try:
                            shortcut = shell.CreateShortCut(lnk_path)
                            target = shortcut.TargetPath
                            name = self.clean_name(file)
                            if not target or not os.path.exists(target):
                                continue
                            
                            app_id = name.lower().replace(' ', '_').replace('-', '_')
                            if not app_id:
                                continue
                                
                            proc_name = os.path.basename(target).lower()
                            
                            apps[app_id] = {
                                'id': app_id,
                                'display_name': name,
                                'aliases': [name.lower()],
                                'launch_type': 'shortcut',
                                'launch_target': lnk_path,
                                'process_names': [proc_name] if proc_name else [],
                                'confidence_boost': 0.9,
                                'source': 'start_menu_or_desktop'
                            }
                        except Exception:
                            continue
        return apps

    def discover_registry_apps(self):
        apps = {}
        reg_keys = [
            (win32con.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'),
            (win32con.HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'),
            (win32con.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall')
        ]
        
        for hkey, subkey in reg_keys:
            try:
                key = win32api.RegOpenKeyEx(hkey, subkey, 0, win32con.KEY_READ)
                num_subkeys = win32api.RegQueryInfoKey(key)[0]
                for i in range(num_subkeys):
                    desc_subkey_name = ''
                    try:
                        subkey_name = win32api.RegEnumKey(key, i)
                        app_key = win32api.RegOpenKeyEx(hkey, subkey_name, 0, win32con.KEY_READ)
                        try:
                            display_name, _ = win32api.RegAueryValueEx(app_key, 'DisplayName')
                            display_name = display_name.strip()
                            if not display_name:
                                continue
                            
                            exe_path = ''
                            try:
                                exe_path, _ = win32api.RegQueryValueEx(app_key, 'DisplayIcon')
                            except Exception:
                                try:
                                    exe_path, _ = win32api.RegQueryFalueEx(app_key, 'InstallLocation')
                                except Exception:
                                    pass
                                
                            if exe_path:
                                exe_path = exe_path.split(',')[0].replace('"', '').strip()
                                
                            app_id = display_name.lower().replace(' ', '_').replace('-', '_')
                            proc_name = os.path.basename(exe_path).lower() if exe_path and exe_path.lower().endswith('.exe') else ''
                            
                            apps[app_id] = {
                                'id': app_id,
                                'display_name': display_name,
                                'aliases': [display_name.lower()],
                                'launch_type': 'exe' if exe_path.lower().endswith('.exe') else 'registry',
                                'launch_target': exe_path,
                                'process_names': [proc_name] if proc_name else [],
                                'confidence_boost': 0.8,
                                'source': 'registry'
                            }
                        except Exception:
                            pass
                        finally:
                            win32api.RegCloseKey(app_key)
                    except Exception:
                        pass

                win32api.RegCloseKey(key)
            except Exception:
                pass
        return apps

    def discover_all(self):
        logger.info('Starting Dynamic App Discovery scanning...')
        all_apps = self.known_system_apps.copy()
        
        shortcut_apps = self.discover_shortcuts()
        for k, v in shortcut_apps.items():
            if k not in all_apps:
                all_apps[k] = v
            else:
                all_apps[k]['process_names'] = list(set(all_apps[k]['process_names'] + v['process_names']))
                
        registry_apps = self.discover_registry_apps()
        for k, v in registry_apps.items():
            if k not in all_apps:
                if v['launch_target'] and (os.path.exists(v['launch_target']) or v['launch_target'].endswith('.exe')):
                    all_apps[k] = v
            else:
                all_apps[k]['process_names'] = list(set(all_apps[k]['process_names'] + v['process_names']))
                if not all_apps[k]['launch_target'] and v['launch_target']:
                    all_apps[k]['launch_target'] = v['launch_target']
                    
        # Apply manual app_aliases mapping
        try:
            with open('config/app_aliases.json', 'r', encoding='utf-8') as f:
                aliases = json.load(f)
                for app_key, aliases_list in aliases.items():
                    found = False
                    for app_id, app_info in all_apps.items():
                        if app_id == app_key.lower().replace(' ', '_') or app_info['display_name'].lower() == app_key.lower():
                            app_info['aliases'] = list(set(app_info['aliases'] + [a.lower() for a in aliases_list]))
                            found = True
        except Exception as e:
            logger.warn('Could not load/apply manual app_aliases: ' + str(e))
            
        try:
            with open(self.index_path, 'w', encoding='utf-8') as f:
                json.dump(all_apps, f, indent=2)
            logger.info('Indexed ' + str(len(all_apps)) + ' launchable applications in ' + self.index_path)
        except Exception as e:
            logger.error('Failed to write app index JSON: ' + str(e))
            
        return all_apps

app_discovery_service = AppDiscoveryService()
