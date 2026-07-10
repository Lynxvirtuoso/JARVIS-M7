import webbrowser
import urllib.parse
from skills.base_skill import BaseSkill
from core.config import config

class BrowserSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "Browser Skill"

    @property
    def description(self) -> str:
        return "Opens websites and performs web searches."

    def matches(self, command: str) -> bool:
        cmd = command.lower()
        return any(x in cmd for x in ["search the web", "search for", "google", "open website", "open youtube", "open github"])

    def execute(self, command: str) -> str:
        cmd = command.lower()
        salutation = config.salutation
        
        # 1. YouTube
        if "open youtube" in cmd:
            webbrowser.open("https://www.youtube.com")
            return f"Opening YouTube, {salutation}."
            
        # 2. GitHub
        elif "open github" in cmd:
            webbrowser.open("https://www.github.com")
            return f"Opening GitHub, {salutation}."
            
        # 3. Search triggers
        elif "search the web for" in cmd or "search for" in cmd or "google" in cmd:
            # Extract query
            query = ""
            for pattern in ["search the web for", "search for", "google"]:
                if pattern in cmd:
                    parts = cmd.split(pattern, 1)
                    if len(parts) > 1:
                        query = parts[1].strip()
                        break
            
            if query:
                url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
                webbrowser.open(url)
                return f"Searching the web for '{query}', {salutation}."
            
        # 4. Open arbitrary website (e.g. "open wikipedia.org")
        if "open" in cmd:
            words = cmd.split()
            for word in words:
                if "." in word and not word.startswith("open"):
                    url = word if word.startswith("http") else f"https://{word}"
                    webbrowser.open(url)
                    return f"Opening {word}, {salutation}."
                    
        webbrowser.open("https://www.google.com")
        return f"Opening default browser, {salutation}."
