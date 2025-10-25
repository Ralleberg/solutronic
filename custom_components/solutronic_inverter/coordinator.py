import logging
from datetime import timedelta

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .solutronic_api import async_get_sensor_data
from .const import DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class SolutronicDataUpdateCoordinator(DataUpdateCoordinator):
    """Koordinator der poller Solutronic inverteren periodisk."""

    def __init__(self, hass, ip_address):
        super().__init__(
            hass,
            _LOGGER,
            name="Solutronic Inverter",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.ip_address = ip_address

    async def _async_update_data(self):
        try:
            data = await async_get_sensor_data(self.ip_address)
            return data
        except Exception as err:
            raise UpdateFailed(f"Error fetching data: {err}") from err

    async def async_validate_connection(self):
        """Valider at IP’en svarer."""
        await async_get_sensor_data(self.ip_address)