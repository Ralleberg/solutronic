from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN
from .coordinator import SolutronicDataUpdateCoordinator


async def async_setup(hass: HomeAssistant, config: dict):
    """Opsætning via configuration.yaml (ikke i brug)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Opsæt integrationen når brugeren har indtastet IP-adressen."""

    ip = entry.data["ip_address"]

    coordinator = SolutronicDataUpdateCoordinator(hass, ip)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # ✅ Nyt API — sætter platforme korrekt op
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unloader integrationen hvis brugeren fjerner den."""
    
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok