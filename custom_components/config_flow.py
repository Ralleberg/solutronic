import socket
import requests
from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN

class SolutronicConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solutronic."""

    def __init__(self):
        """Initialize."""
        self._host = None

    async def async_step_user(self, user_input=None):
        """Handle the initial user input."""
        if user_input is None:
            # Scan network for devices
            devices = await self.async_find_solutronic_devices()
            if devices:
                return self.async_show_form(
                    step_id="user",
                    data_schema=self._build_data_schema(devices),
                    description_placeholders={"devices": ", ".join(devices)},
                )
            else:
                # No devices found, ask user for IP
                return self.async_show_form(
                    step_id="user", 
                    data_schema=self._build_data_schema([]),
                    errors={"base": "no_devices_found"}
                )
        
        # If the user provided an IP address
        self._host = user_input.get("host")
        return self.async_create_entry(title="Solutronic", data={"host": self._host})

    def _build_data_schema(self, devices):
        """Build the data schema for the form."""
        from homeassistant.helpers import config_validation as cv
        from homeassistant.components import InputText

        schema = {}
        if devices:
            schema["host"] = cv.string
        else:
            schema["host"] = cv.string
        return schema

    async def async_find_solutronic_devices(self, timeout=2):
        """Scan the local subnet for Solutronic devices."""
        devices = []

        # Get the local subnet
        subnet = get_local_subnet()
        if not subnet:
            print("Could not determine local subnet.")
            return devices

        # Scan each IP in the subnet
        for ip in subnet.hosts():
            try:
                response = requests.get(f"http://{ip}", timeout=timeout)
                if "solutronic" in response.text.lower():
                    devices.append(str(ip))
            except (requests.ConnectionError, requests.Timeout):
                continue

        return devices