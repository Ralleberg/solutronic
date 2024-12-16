"""Solutronic integration for Home Assistant"""

from homeassistant.core import Config, HomeAssistant

DOMAIN = "solutronic"


async def async_setup(hass: HomeAssistant, config: Config):
    """Set up the Solutronic integration."""
    hass.data[DOMAIN] = {}
    return True
