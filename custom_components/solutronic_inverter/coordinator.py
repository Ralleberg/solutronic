import logging
from datetime import timedelta

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .solutronic_api import async_get_sensor_data, async_get_raw_html, async_get_mac
from .discovery import discover_solutronic  # used for auto-reconnect scan

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

        # Used to avoid repeating bridge-mode warning log
        self._bridge_warning_logged = False

        # Default device metadata (will be replaced automatically after first fetch)
        self.device_manufacturer = "Solutronic"
        self.device_model = "Unknown model"
        self.device_firmware = "Unknown"

    async def _async_update_data(self):
        """Fetch data and return fallback data if device is temporarily unreachable."""
        try:
            # Request data from the inverter (parsed sensor values)
            data = await async_get_sensor_data(self.ip_address)

            # --- Extract serial number (SN) and ensure no decimal formatting ---
            sn = data.get("SN")

            if sn is not None:
                try:
                    # Convert to clean integer string if value was a float like "2091.0"
                    self.device_serial = str(int(float(sn)))
                except Exception:
                    # Fallback: just convert to string
                    self.device_serial = str(sn).strip()
            else:
                self.device_serial = None

            # --- Normalize stored IP address (ensure it's clean and exact) ---
            self.device_ip = self.ip_address

            # --- Parse device metadata from raw HTML ---
            try:
                html = await async_get_raw_html(self.ip_address)

                # Extract manufacturer and model from <h1> header
                if "<h1>" in html:
                    header = html.split("<h1>")[1].split("</h1>")[0]
                    parts = [line.strip() for line in header.replace("<br>", "\n").split("\n") if line.strip()]
                    if len(parts) >= 2:
                        self.device_model = parts[0]
                        self.device_manufacturer = parts[1]

                # Extract firmware version
                if "FW-Release" in html:
                    fw_line = html.split("FW-Release:")[1].split("<")[0].strip()
                    self.device_firmware = fw_line

            except Exception:
                # Metadata parsing errors should never stop telemetry updates
                pass

            # --- Fail-safe total AC power calculation (PAC_TOTAL) ---
            pac_values = []
            for key in ("PACL1", "PACL2", "PACL3"):
                value = data.get(key)
                if isinstance(value, (int, float)):
                    pac_values.append(value)

            if pac_values:
                data["PAC_TOTAL"] = sum(pac_values)
            else:
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

            # ---- Docker Bridge Mode Detection (no ARP visibility) ----
            try:
                mac = await async_get_mac(self.ip_address)
                if mac is None and not self._bridge_warning_logged:
                    _LOGGER.warning(
                        "Auto-reconnect disabled: Home Assistant appears to be running in Docker bridge mode "
                        "(no ARP visibility). The integration will continue working, "
                        "but automatic IP recovery will not be available. "
                        "Use host network mode to enable auto-reconnect."
                    )
                    self._bridge_warning_logged = True
            except Exception:
                pass

            # ---- Controlled fallback data behavior ----

            last = self._last_data or {}

            # Keys that should retain last known values (energy data)
            retain_keys = ["ET", "EG"]  # Daily + Lifetime energy

            # Keys that should be zero when inverter is offline
            zero_keys = [
                "PAC", "PAC_TOTAL",
                "PACL1", "PACL2", "PACL3",
                "UDC1", "UDC2", "UDC3",
                "IDC1", "IDC2", "IDC3",
                "MAXP", "ETA",
                "UACL1", "UACL2", "UACL3",
            ]

            fallback = {}

            # Set zero-values for momentary readings
            for key in zero_keys:
                fallback[key] = 0

            # Restore ET + EG (energy totals) if known
            for key in retain_keys:
                fallback[key] = last.get(key, 0)

            self._last_data = fallback
            return fallback

    async def async_validate_connection(self):
        """Used by config flow to verify connectivity before setup."""
        await async_get_sensor_data(self.ip_address)