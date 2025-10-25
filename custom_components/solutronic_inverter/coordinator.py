import logging
from datetime import timedelta

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .solutronic_api import async_get_sensor_data, async_get_raw_html

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

        # Default device metadata (will be replaced automatically after first fetch)
        self.device_manufacturer = "Solutronic"
        self.device_model = "Unknown model"
        self.device_firmware = "Unknown"

    async def _async_update_data(self):
        """Fetch data and return fallback data if device is temporarily unreachable."""
        try:
            # Request data from the inverter (parsed sensor values)
            data = await async_get_sensor_data(self.ip_address)

            # --- Parse device metadata from raw HTML ---
            try:
                html = await async_get_raw_html(self.ip_address)

                # Extract manufacturer and model from <h1> header
                # Example: <h1>SOLPLUS 100<br>Solutronic AG</h1>
                if "<h1>" in html:
                    header = html.split("<h1>")[1].split("</h1>")[0]
                    parts = [line.strip() for line in header.replace("<br>", "\n").split("\n") if line.strip()]
                    if len(parts) >= 2:
                        self.device_model = parts[0]
                        self.device_manufacturer = parts[1]

                # Extract firmware version
                # Example: FW-Release: 1.42
                if "FW-Release" in html:
                    fw_line = html.split("FW-Release:")[1].split("<")[0].strip()
                    self.device_firmware = fw_line

            except Exception:
                # Metadata parsing errors should never stop telemetry updates
                pass

            # --- Fail-safe total AC power calculation (PAC_TOTAL) ---
            # Sum only the phases that exist and contain numeric values.
            pac_values = []
            for key in ("PACL1", "PACL2", "PACL3"):
                value = data.get(key)
                if isinstance(value, (int, float)):
                    pac_values.append(value)

            if pac_values:
                # At least one valid phase available → calculate total
                data["PAC_TOTAL"] = sum(pac_values)
            else:
                # No valid phase data → remove PAC_TOTAL to avoid "unavailable"
                data.pop("PAC_TOTAL", None)

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