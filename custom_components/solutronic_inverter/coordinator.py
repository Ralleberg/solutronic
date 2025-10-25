import logging
from datetime import timedelta

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .solutronic_api import async_get_sensor_data

_LOGGER = logging.getLogger(__name__)


class SolutronicDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator that polls the Solutronic inverter and provides stable data."""

    def __init__(self, hass, ip_address, scan_interval):
        # Initialize coordinator with dynamic polling interval
        super().__init__(
            hass,
            _LOGGER,
            name="Solutronic Inverter",
            update_interval=timedelta(seconds=scan_interval),
        )

        self.ip_address = ip_address
        self._last_data = None  # Store last known valid data for fallback

        # Dynamic device identity fields (set after first update)
        self.manufacturer = "Solutronic"
        self.model = "Inverter"

    async def _async_update_data(self):
        """Fetch data and return fallback data if device is temporarily unreachable."""
        try:
            # Request data from the inverter
            data = await async_get_sensor_data(self.ip_address)

            # Store dynamic manufacturer/model if available
            # These keys are injected by solutronic_api.py
            self.manufacturer = data.get("_manufacturer", self.manufacturer)
            self.model = data.get("_model", self.model)

            # Calculate total AC power (PAC_TOTAL) if all phases are present
            if all(k in data for k in ("PACL1", "PACL2", "PACL3")):
                try:
                    data["PAC_TOTAL"] = data["PACL1"] + data["PACL2"] + data["PACL3"]
                except Exception:
                    # If conversion fails, ignore calculation silently
                    pass

            # Store latest valid dataset for fallback use
            self._last_data = data
            return data

        except Exception as err:
            # Log failure (not as error to avoid log spam)
            _LOGGER.warning(
                "Failed to fetch data from Solutronic inverter (%s): %s",
                self.ip_address,
                err,
            )

            # Use previous dataset to prevent sensors from showing 'unknown'
            if self._last_data is not None:
                return self._last_data

            # If no previous data exists, raise failure for Home Assistant to handle
            raise UpdateFailed(f"Unable to fetch data from inverter: {err}") from err

    async def async_validate_connection(self):
        """Used by config flow to verify connectivity before setup."""
        await async_get_sensor_data(self.ip_address)