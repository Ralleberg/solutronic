"""The Solutronic integration"""

from homeassistant import config_entries, core

DOMAIN = "solutronic"

async def async_setup(hass: core.HomeAssistant, config: dict):
    """Set up the Solutronic component"""
    return True
