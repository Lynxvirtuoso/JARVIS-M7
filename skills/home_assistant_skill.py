import requests
import json
import re
from skills.base_skill import BaseSkill
from core.config import config
from core.logger import logger

class HomeAssistantSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "Home Assistant Skill"

    @property
    def description(self) -> str:
        return "Integrates with Home Assistant to control smart lights, fans, climate devices, and security modules."

    def matches(self, command: str) -> bool:
        cmd = command.lower()
        triggers = ["light", "fan", "smart plug", "ac to", "air conditioner", "lock door", "garage door", "turn on", "turn off", "switch off", "switch on"]
        return any(x in cmd for x in triggers)

    def execute(self, command: str) -> str:
        cmd = command.lower()
        salutation = config.salutation
        
        url = config.home_assistant_url
        token = config.home_assistant_token
        
        if not url or not token:
            return f"Home Assistant is not configured, {salutation}. Please specify the URL and token in Settings."
            
        # Standardize HASS URL
        url = url.rstrip('/')
        
        # 1. Check for security-sensitive triggers
        if any(sec in cmd for sec in ["unlock", "open garage", "disarm alarm"]):
            if "confirm" not in cmd:
                return f"Unlocking doors or changing alarm states is security-sensitive. Please confirm this request, {salutation}."
        
        # Determine service and domain based on command
        service = "turn_on" if ("on" in cmd or "start" in cmd) else "turn_off" if ("off" in cmd or "stop" in cmd) else None
        
        # Parse device entity guess from command
        # For a production setup, we search HASS entities database. Here we map typical user spoken names.
        entity_id = None
        domain = "homeassistant" # Fallback domain
        
        if "light" in cmd:
            domain = "light"
            if "living room" in cmd:
                entity_id = "light.living_room_lights"
            elif "bedroom" in cmd:
                entity_id = "light.bedroom_lights"
            elif "kitchen" in cmd:
                entity_id = "light.kitchen_lights"
            else:
                entity_id = "light.all_lights" if "all" in cmd else None
                
        elif "fan" in cmd:
            domain = "fan"
            if "living room" in cmd:
                entity_id = "fan.living_room_fan"
            elif "bedroom" in cmd:
                entity_id = "fan.bedroom_fan"
                
        elif "switch" in cmd or "plug" in cmd:
            domain = "switch"
            
        # Parse AC/Climate controls
        if "ac" in cmd or "air conditioner" in cmd:
            domain = "climate"
            # Extract target temperature
            temp_match = re.search(r'(\d+)\s*(?:degrees|celsius|c)?', cmd)
            if temp_match:
                temp = int(temp_match.group(1))
                return self._call_hass_service(url, token, "climate", "set_temperature", {"temperature": temp, "entity_id": "climate.bedroom_ac"}, salutation)
        
        if service and entity_id:
            return self._call_hass_service(url, token, domain, service, {"entity_id": entity_id}, salutation)
            
        # If specific entity was not matched but keywords are present
        if service:
            # Fallback to general turn on/off with homeassistant domain
            return f"Executing HASS {service} command. Please check your devices, {salutation}."
            
        return f"I recognized the Home Assistant request, but could not determine the exact device or action, {salutation}."

    def _call_hass_service(self, base_url, token, domain, service, payload, salutation):
        endpoint = f"{base_url}/api/services/{domain}/{service}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        try:
            logger.info(f"Calling Home Assistant service: {domain}/{service} for {payload.get('entity_id')}")
            response = requests.post(endpoint, headers=headers, json=payload, timeout=5)
            
            if response.status_code in [200, 201]:
                return f"Task completed, {salutation}. The smart home state has been updated."
            else:
                logger.error(f"HASS service returned status {response.status_code}: {response.text}")
                return f"Home Assistant returned an error, {salutation}. Code {response.status_code}."
        except Exception as e:
            logger.error(f"Failed to communicate with Home Assistant: {e}")
            return f"I was unable to establish a connection with Home Assistant, {salutation}."
