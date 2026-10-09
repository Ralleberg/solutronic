"""Diagnostics for troubleshooting without exposing inverter identifiers."""

from urllib.parse import urlsplit

from homeassistant.components.diagnostics import async_redact_data

from .const import DOMAIN
from .sensor import SENSORS
from .util import as_float, scan_interval


async def async_get_config_entry_diagnostics(hass, entry):
    """Return selected configuration, connection health and numeric readings."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    diagnostics = {
        "configuration": {
            "ip_address": entry.data.get("ip_address"),
            "scan_interval": scan_interval(entry.options),
        },
    }
    if coordinator is not None:
        endpoint = urlsplit(coordinator.device_url)
        diagnostics.update(
            {
                "device": {
                    "manufacturer": coordinator.device_manufacturer,
                    "model": coordinator.device_model,
                    "firmware": coordinator.device_firmware,
                    "serial": coordinator.device_serial,
                },
                "connection": {
                    "reachable": coordinator.last_successful_update is not None
                    and coordinator.consecutive_failures == 0,
                    "last_successful_update": (
                        coordinator.last_successful_update.isoformat()
                        if coordinator.last_successful_update
                        else None
                    ),
                    "last_error_type": coordinator.last_error_type,
                    "consecutive_failures": coordinator.consecutive_failures,
                    "endpoint_port": endpoint.port or 80,
                    "endpoint_path": endpoint.path,
                    "poll_interval_seconds": (
                        coordinator.update_interval.total_seconds()
                    ),
                },
                "supported_sensor_keys": sorted(
                    coordinator.supported_keys & SENSORS.keys()
                ),
                "sensor_data": {
                    key: as_float(value)
                    for key, value in (coordinator.data or {}).items()
                    if key in SENSORS
                },
                "energy_counter": {
                    "total": coordinator._lt_total,
                    "previous_daily": coordinator._lt_prev_et,
                },
            }
        )
    return async_redact_data(diagnostics, {"ip_address", "serial"})
