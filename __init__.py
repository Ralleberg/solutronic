from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery
from .const import DOMAIN

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Solutronic integration."""
    hass.data[DOMAIN] = {}
    discovery.load_platform(hass, "sensor", DOMAIN, {}, config)
    return True