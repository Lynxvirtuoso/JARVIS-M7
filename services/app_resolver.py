import os
import sys
import json
from dataclasses import dataclass
from difflib import SequenceMatcher
from core.logger import logger
from core.config import config

@dataclass
class AppMatch:
    app_id: str
    display_name: str
    launch_target: str
    process_names: list[str]
    confidence: float
    match_reason: str

class AppResolver:
    def __init__(self, index_path='data/app_index.json'):
        self.index_path = index_path

    def get_builtin_fallback_apps(self):
        fallback_list = [
            {
                "id": "notepad",
                "display_name": "Notepad",
                "aliases": ["notepad", "note pad", "notes"],
                "launch_type": "exe",
                "launch_target": "notepad.exe",
                "process_names": ["notepad.exe"],
                "source": "builtin"
            },
            {
                "id": "edge",
                "display_name": "Microsoft Edge",
                "aliases": ["edge", "microsoft edge", "ms edge", "edge browser"],
                "launch_type": "exe",
                "launch_target": "msedge.exe",
                "process_names": ["msedge.exe"],
                "source": "builtin"
            },
            {
                "id": "chrome",
                "display_name": "Google Chrome",
                "aliases": ["chrome", "google chrome", "browser"],
                "launch_type": "exe",
                "launch_target": "chrome.exe",
                "process_names": ["chrome.exe"],
                "source": "builtin"
            },
            {
                "id": "calculator",
                "display_name": "Calculator",
                "aliases": ["calculator", "calc"],
                "launch_type": "exe",
                "launch_target": "calc.exe",
                "process_names": ["CalculatorApp.exe", "calc.exe"],
                "source": "builtin"
            },
            {
                "id": "file_explorer",
                "display_name": "File Explorer",
                "aliases": ["file explorer", "explorer", "windows explorer", "files"],
                "launch_type": "exe",
                "launch_target": "explorer.exe",
                "process_names": ["explorer.exe"],
                "source": "builtin"
            },
            {
                "id": "task_manager",
                "display_name": "Task Manager",
                "aliases": ["task manager", "taskmgr"],
                "launch_type": "exe",
                "launch_target": "taskmgr.exe",
                "process_names": ["Taskmgr.exe", "taskmgr.exe"],
                "source": "builtin"
            },
            {
                "id": "powershell",
                "display_name": "PowerShell",
                "aliases": ["powershell", "power shell"],
                "launch_type": "exe",
                "launch_target": "powershell.exe",
                "process_names": ["powershell.exe"],
                "source": "builtin"
            },
            {
                "id": "command_prompt",
                "display_name": "Command Prompt",
                "aliases": ["command prompt", "cmd"],
                "launch_type": "exe",
                "launch_target": "cmd.exe",
                "process_names": ["cmd.exe"],
                "source": "builtin"
            }
        ]
        return {item["id"]: item for item in fallback_list}

    def load_index(self):
        try:
            if not os.path.exists(self.index_path):
                from services.app_discovery_service import app_discovery_service
                app_discovery_service.discover_all()
                
            with open(self.index_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.exception(f"App index load failed: {e}")
            logger.info("App index load failed, using builtin fallback app registry.")
            return self.get_builtin_fallback_apps()

    def resolve_app(self, user_text: str) -> AppMatch:
        user_text = user_text.lower().strip()
        index = self.load_index()
        
        matches = []
        
        for app_id, app_info in index.items():
            disp_name = app_info['display_name'].lower().strip()
            aliases = [a.lower().strip() for a in app_info.get('aliases', [])]
            boost = app_info.get('confidence_boost', 1.0)
            
            # 1. Exact alias match
            if user_text in aliases:
                matches.append(AppMatch(
                    app_id=app_id,
                    display_name=app_info['display_name'],
                    launch_target=app_info['launch_target'],
                    process_names=app_info['process_names'],
                    confidence=1.0 * boost,
                    match_reason='Exact alias match'
                ))
                continue
                
            # 2. Exact display name match
            if user_text == disp_name:
                matches.append(AppMatch(
                    app_id=app_id,
                    display_name=app_info['display_name'],
                    launch_target=app_info['launch_target'],
                    process_names=app_info['process_names'],
                    confidence=0.98 * boost,
                    match_reason='Exact display name match'
                ))
                continue
                
            # 3. Starts-with / Contains match
            if disp_name.startswith(user_text) or user_text.startswith(disp_name):
                matches.append(AppMatch(
                    app_id=app_id,
                    display_name=app_info['display_name'],
                    launch_target=app_info['launch_target'],
                    process_names=app_info['process_names'],
                    confidence=0.9 * boost,
                    match_reason='Starts-with match'
                ))
                continue
                
            if user_text in disp_name:
                matches.append(AppMatch(
                    app_id=app_id,
                    display_name=app_info['display_name'],
                    launch_target=app_info['launch_target'],
                    process_names=app_info['process_names'],
                    confidence=0.85 * boost,
                    match_reason='Contains match'
                ))
                continue
                
            # 4. Token / Word intersection match
            user_words = set(user_text.split())
            disp_words = set(disp_name.split())
            common_words = user_words.intersection(disp_words)
            if common_words:
                ratio = len(common_words) / max(len(user_words), len(disp_words))
                if ratio >= 0.5:
                    matches.append(AppMatch(
                        app_id=app_id,
                        display_name=app_info['display_name'],
                        launch_target=app_info['launch_target'],
                        process_names=app_info['process_names'],
                        confidence=0.8 * ratio * boost,
                        match_reason='Token match'
                    ))
                    continue

            # 5. Fuzzy match against display name and aliases
            best_ratio = 0.0
            for alias in aliases + [disp_name]:
                r = SequenceMatcher(None, user_text, alias).ratio()
                if r > best_ratio:
                    best_ratio = r
                    
            if best_ratio >= 0.75:
                matches.append(AppMatch(
                    app_id=app_id,
                    display_name=app_info['display_name'],
                    launch_target=app_info['launch_target'],
                    process_names=app_info['process_names'],
                    confidence=best_ratio * boost,
                    match_reason='Fuzzy match'
                ))

        if not matches:
            return None
            
        # Sort by confidence descending
        matches.sort(key=lambda m: m.confidence, reverse=True)
        
        # Log resolution
        logger.info('Resolved app request ' + str(user_text) + ' to ' + str(matches[0].display_name) + ' with confidence ' + str(matches[0].confidence))
        return matches[0]

app_resolver = AppResolver()
