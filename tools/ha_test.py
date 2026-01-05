import requests
from core.config import cfg as config

# Load Home Assistant configuration from env vars
HASS_URL = config["HA"]["HASS_URL"]
HASS_TOKEN = config["HA"]["HASS_TOKEN"]
LIGHT_ENTITY = config["HA_TOOLS"]["LIGHT_ENTITY"]
TEMPERATURE_ENTITY = config["HA_TOOLS"]["TEMPERATURE_ENTITY"]
HUMIDITY_ENTITY = config["HA_TOOLS"]["HUMIDITY_ENTITY"]
AMBIENT_LIGHT_ENTITY = config["HA_TOOLS"]["AMBIENT_LIGHT_ENTITY"]
SOUND_LEVEL_ENTITY = config["HA_TOOLS"]["SOUND_LEVEL_ENTITY"]
HEADERS = {"Authorization": f"Bearer {HASS_TOKEN}", "Content-Type": "application/json"}

class HomeAssistant():
    def get_temperature(self) -> str:
        """Retrieves the current room temperature from Home Assistant."""
        url = f"{HASS_URL}/api/states/{TEMPERATURE_ENTITY}"
        try:
            response = requests.get(url, headers=HEADERS)
            if response.status_code == 200:
                data = response.json()
                temperature = data.get("state", "unknown")
                # return f"The room temperature is {temperature}°C."
                return {
                    'room_temperature': temperature + '°C'
                }
            else:
                return f"Failed to retrieve temperature: {response.status_code} - {response.text}"
        except Exception as e:
            return f"Error retrieving temperature: {str(e)}"

    def get_humidity(self) -> str:
        """Retrieves the current room humidity from Home Assistant."""
        url = f"{HASS_URL}/api/states/{HUMIDITY_ENTITY}"
        try:
            response = requests.get(url, headers=HEADERS)
            if response.status_code == 200:
                data = response.json()
                humidity = data.get("state", "unknown")
                # return f"The room humidity is {humidity}%."
                return {
                    'room_humidity': humidity + '%'
                }
            else:
                return f"Failed to retrieve humidity: {response.status_code} - {response.text}"
        except Exception as e:
            return f"Error retrieving humidity: {str(e)}"

    def get_ambient_light(self):
        url = f"{HASS_URL}/api/states/{AMBIENT_LIGHT_ENTITY}"
        try:
            response = requests.get(url, headers=HEADERS)
            if response.status_code == 200:
                data = response.json()
                ambient_light = data.get("state", "unknown")
                return f"The ambient light level is {ambient_light}."
            else:
                return f"Failed to retrieve ambient light: {response.status_code} - {response.text}"
        except Exception as e:
            return f"Error retrieving ambient light: {str(e)}"

    def get_sound_level(self):
        url = f"{HASS_URL}/api/states/{SOUND_LEVEL_ENTITY}"
        try:
            response = requests.get(url, headers=HEADERS)
            if response.status_code == 200:
                data = response.json()
                sound_level = data.get("state", "unknown")
                return f"The sound level in the room is {sound_level}."
            else:
                return f"Failed to retrieve sound level: {response.status_code} - {response.text}"
        except Exception as e:
            return f"Error retrieving sound level: {str(e)}"

    def toggle_wled(self) -> str:
        """Toggles the WLED light on or off using Home Assistant."""
        url = f"{HASS_URL}api/services/light/toggle"
        payload = {"entity_id": LIGHT_ENTITY}

        # print(f"🔍 DEBUG: Sending request to {url} with payload: {payload}")
        
        try:
            response = requests.post(url, headers=HEADERS, json=payload)
            # print(f"🔍 DEBUG: Response Code: {response.status_code}, Response: {response.text}")
            
            if response.status_code == 200:
                return {'response': "WLED toggled successfully!"}
            else:
                return {'response': f"Failed to toggle WLED: {response.status_code} - {response.text}"}
        except Exception as e:
            return {'response': f"Error toggling WLED: {str(e)}"}

    def set_wled_effect(self, effect_name, brightness=None, color=None):
        """
        Set the WLED effect, optionally also setting brightness and RGB color.
        - effect_name: Name of the effect (as string, must be in the effect_list).
        - brightness: Integer (0-255)
        - color: Hex string like "#FFAA00"
        """
        try:
            data = {
                "entity_id": LIGHT_ENTITY,
                "effect": effect_name
            }

            if brightness is not None:
                data["brightness"] = brightness

            if color:
                if not color.startswith("#") or len(color) != 7:
                    return "Invalid color format. Use hex format, e.g., #FFAA00."
                data["rgb_color"] = [
                    int(color[1:3], 16),
                    int(color[3:5], 16),
                    int(color[5:7], 16)
                ]

            response = requests.post(
                f"{HASS_URL}services/light/turn_on",
                headers=HEADERS,
                json=data
            )

            if response.status_code == 200:
                return f"WLED effect set to '{effect_name}'" + (
                    f", brightness {brightness}" if brightness else ""
                ) + (f", color {color}" if color else "") + "."
            else:
                return f"Failed to update WLED: {response.text}"
        except Exception as e:
            return f"Error setting WLED effect: {str(e)}"

    def get_light_state(self) -> str:
        """Checks the current state of the WLED light (on/off)."""
        url = f"{HASS_URL}api/states/{LIGHT_ENTITY}"

        # print(f"🔍 DEBUG: Sending GET request to {url}")
        
        try:
            response = requests.get(url, headers=HEADERS)
            # print(f"🔍 DEBUG: Response Code: {response.status_code}, Response: {response.text}")

            if response.status_code == 200:
                data = response.json()
                state = data.get("state", "unknown").lower()
                
                if state == "on":
                    return {"response": "The lights are currently ON."}
                elif state == "off":
                    return {"response": "The lights are currently OFF."}
                else:
                    return {"response": f"The light's state is {state}."}
            else:
                return {"response": f"Failed to retrieve light state: {response.status_code} - {response.text}"}
        except Exception as e:
            return {"response": f"Error retrieving light state: {str(e)}"}
    
    def ensure_wled_state(self, desired_state: str) -> dict:
        """
        Ensures the WLED light reaches a desired state ("on" or "off").

        This function is designed for use by an AI agent that needs reliable,
        state-aware control over WLED lighting through Home Assistant.

        Behavior:
        1. It first checks the current light state using `get_light_state()`.
        (This is always done to avoid unnecessary toggling.)
        2. If the light is already in the desired state, it returns a confirmation
        without making any changes.
        3. If the light is *not* in the desired state, it calls `toggle_wled()`
        to switch the light.
        4. It verifies the final state and returns a structured response.

        Parameters
        ----------
        desired_state : str
            The state you want the light to be in. Accepts:
            - "on"
            - "off"

        Returns
        -------
        dict
            A dictionary containing a human-readable message describing what
            occurred, including errors if they happen.

        Example
        -------
        >>> ensure_wled_state("on")
        {'response': 'WLED was OFF and has now been turned ON.'}

        Notes
        -----
        - This function relies on the existing helper functions:
            * `get_light_state()`
            * `toggle_wled()`
        - The function uses text parsing because `get_light_state()` returns a
        sentence rather than a raw state value.
        """
        
        desired_state = desired_state.lower().strip()
        if desired_state not in ("on", "off"):
            return {"response": f"Invalid desired_state '{desired_state}'. Use 'on' or 'off'."}

        # Step 1: Check current state
        state_info = self.get_light_state()
        state_text = state_info.get("response", "").lower()

        if "on" in state_text:
            current = "on"
        elif "off" in state_text:
            current = "off"
        else:
            return {"response": f"Could not determine light state. Raw response: {state_text}"}

        # Step 2: If already in the desired state, do nothing
        if current == desired_state:
            return {"response": f"WLED is already {desired_state.upper()}."}

        # Step 3: Toggle if needed
        toggle_result = self.toggle_wled()
        toggle_text = toggle_result.get("response", "")

        # Step 4: Verify new state
        final_state_text = self.get_light_state().get("response", "").lower()
        if desired_state in final_state_text:
            return {"response": f"WLED was {current.upper()} and has now been turned {desired_state.upper()}."}
        else:
            return {
                "response": (
                    f"Tried to change WLED from {current.upper()} to {desired_state.upper()}, "
                    f"but it may not have succeeded. Toggle result: {toggle_text}"
                )
            }