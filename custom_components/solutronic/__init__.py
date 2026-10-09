import logging

from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY, ConfigEntry
from homeassistant.const import (
    ATTR_RESTORED,
    EVENT_HOMEASSISTANT_STARTED,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntry

from .const import DOMAIN
from .coordinator import SolutronicDataUpdateCoordinator
from .discovery import async_discover_inverters
from .util import scan_interval

_LOGGER = logging.getLogger(__name__)
_DISCOVERY_STARTED = f"{DOMAIN}_discovery_started"


async def _async_discover_on_start(hass):
    """Offer discovered-device cards once the integration has been loaded."""
    try:
        candidates = await async_discover_inverters(hass)
    except Exception:
        _LOGGER.debug("Solutronic startup discovery failed", exc_info=True)
        return
    for candidate in candidates:
        try:
            await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_INTEGRATION_DISCOVERY},
                data={"ip_address": candidate.ip_address},
            )
        except Exception:
            _LOGGER.debug("Could not start Solutronic discovery flow", exc_info=True)


async def async_setup(hass: HomeAssistant, config: dict):
    """Schedule one discovery pass after HA startup; manual setup stays available."""
    if hass.data.get(_DISCOVERY_STARTED):
        return True
    hass.data[_DISCOVERY_STARTED] = True

    @callback
    def start_discovery(event=None):
        task = hass.async_create_task(_async_discover_on_start(hass))

        @callback
        def cancel_discovery(event):
            task.cancel()

        remove_stop_listener = hass.bus.async_listen(
            EVENT_HOMEASSISTANT_STOP, cancel_discovery
        )
        task.add_done_callback(lambda _: remove_stop_listener())

    if hass.is_running:
        start_discovery()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, start_discovery)
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Reload for connection/options changes, not metadata updates."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is not None and (
        coordinator.ip_address != entry.data["ip_address"]
        or coordinator.options != dict(entry.options)
    ):
        await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up the integration from a config entry."""

    # Get IP stored from config flow
    ip = entry.data["ip_address"]

    # Read polling interval from integration options UI
    interval = scan_interval(entry.options)

    # Create the data coordinator with dynamic interval
    coordinator = SolutronicDataUpdateCoordinator(hass, ip, interval, entry)
    await coordinator.async_restore_state()
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
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_save_state()
    return unload_ok


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> bool:
    """Allow user removal of a stale device, protecting current/loaded entities."""
    if (DOMAIN, entry.entry_id) in device.identifiers or not any(
        domain == DOMAIN for domain, _ in device.identifiers
    ):
        # The current inverter is tied to the config entry, even during outages.
        return False

    registry = er.async_get(hass)
    for entity in er.async_entries_for_device(
        registry, device.id, include_disabled_entities=True
    ):
        if (
            entity.platform != DOMAIN
            or entity.config_entry_id != entry.entry_id
            or entity.unique_id.startswith(f"{entry.entry_id}_")
        ):
            return False
        state = hass.states.get(entity.entity_id)
        if state is not None and not state.attributes.get(ATTR_RESTORED):
            # Loaded legacy entities are also protected. A restored unavailable
            # placeholder alone does not mean an entity is still being provided.
            return False

    # HA removes the selected device and its stale entities after UI confirmation.
    # Do not delete registries here or trigger a reload of the working entry.
    return True
