import os
import json
import urllib.request
import urllib.parse
from core.config import config
from core.logger import logger

def search_tavily(query: str) -> list[str]:
    """
    Performs a web search using the Tavily Search API and returns a list of result snippets.
    Loads API key from TAVILY_API_KEY environment variable.
    """
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = (os.getenv("TAVILY_API_KEY") or "").strip()
    if not api_key:
        logger.warning("Tavily API key not found in environment (TAVILY_API_KEY). Skipping web search.")
        return ["Web search skipped: Tavily API key not configured."]

    url = "https://api.tavily.com/search"
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "basic",
        "max_results": 5
    }
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10.0) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                results = []
                for item in data.get("results", []):
                    title = item.get("title", "")
                    content = item.get("content", "")
                    results.append(f"{title}: {content}")
                return results
            else:
                logger.error(f"Tavily search returned status: {response.status}")
                return [f"Tavily search failed with status {response.status}."]
    except Exception as e:
        logger.error(f"Tavily search API call failed: {e}", exc_info=True)
        return [f"Tavily search error: {e}"]
