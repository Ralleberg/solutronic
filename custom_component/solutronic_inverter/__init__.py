from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL
from .coordinator import SolutronicDataUpdateCoordinator


async def async_setup(hass: HomeAssistant, config: dict):
    """Setup via configuration.yaml (not used)."""
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Reload the integration when options (e.g. scan_interval) are changed."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up the integration from a config entry."""

    # Get IP stored from config flow
    ip = entry.data["ip_address"]

    # Read polling interval from integration options UI
    scan_interval = entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)

    # Create the data coordinator with dynamic interval
    coordinator = SolutronicDataUpdateCoordinator(hass, ip, scan_interval)
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator instance
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Forward setup to sensor platform(s)
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    # Automatically reload integration when options change
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload integration when removed."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok