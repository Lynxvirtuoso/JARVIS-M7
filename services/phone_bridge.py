import requests
from core.config import config
from core.logger import logger

def trigger_phone_call(number: str) -> tuple[bool, str]:
    """
    Sends an HTTP GET request to the Android bridge app's embedded HTTP server
    to initiate a direct phone call.
    """
    phone_ip = config.get("phone_ip", "").strip()
    token = config.get("phone_call_token", "").strip()
    
    if not phone_ip:
        return False, "Phone IP address is not configured. Please set it in settings."
        
    url = f"http://{phone_ip}:8765/dial"
    params = {
        "number": number,
        "token": token
    }
    
    logger.info(f"Requesting phone bridge call trigger: {url} (number: {number})")
    try:
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            logger.info(f"Phone bridge accepted dial command: {response.text}")
            return True, response.text
        elif response.status_code == 403:
            logger.error("Phone bridge returned 403 Forbidden. Invalid token.")
            return False, "The security token configured in settings was rejected by your phone."
        else:
            logger.error(f"Phone bridge returned status {response.status_code}: {response.text}")
            return False, f"Phone bridge returned error status {response.status_code}."
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to connect to phone bridge at {phone_ip}: {e}")
        return False, "I couldn't reach your phone to place the call, Sir. Please check that it is on the same Wi-Fi network and the app is running."
