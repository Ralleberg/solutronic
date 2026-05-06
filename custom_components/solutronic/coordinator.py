import logging
import re
from datetime import timedelta

from bs4 import BeautifulSoup
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .solutronic_api import async_get_sensor_data, async_get_raw_html

_LOGGER = logging.getLogger(__name__)


def _as_float(value, default=0.0):
    """Return value as float, or default when the inverter reports unexpected data."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class SolutronicDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator that polls the Solutronic inverter and provides stable data."""

    def __init__(self, hass, ip_address, scan_interval, entry=None):
        # Initialize coordinator with dynamic polling interval
        super().__init__(
            hass,
            _LOGGER,
            name="Solutronic",
            update_interval=timedelta(seconds=scan_interval),
        )

        self.ip_address = ip_address
        self.hass = hass
        self.entry = entry
        self._last_data = None  # Store last known valid data for fallback
        self.supported_keys = set()

        # Lifetime counter internal state
        self._lt_prev_et = None
        self._lt_total = None

        self._offline_logged = False

        # Device metadata (persisted in config entry when available)
        if entry is not None:
            self.device_manufacturer = entry.data.get("manufacturer", "Solutronic")
            self.device_model = entry.data.get("model", "Unknown model")
            self.device_firmware = entry.data.get("firmware", "Unknown")
            self.device_serial = entry.data.get("serial", None)
        else:
            self.device_manufacturer = "Solutronic"
            self.device_model = "Unknown model"
            self.device_firmware = "Unknown"
            self.device_serial = None

    async def _async_update_data(self):
        """Fetch data and return fallback data if device is temporarily unreachable."""
        try:
            # Request data from the inverter (parsed sensor values)
            data = await async_get_sensor_data(self.ip_address, self.hass)

            # --- Extract serial number (SN) and ensure no decimal formatting ---
            sn = data.get("SN")
            if sn is not None:
                try:
                    # Convert to clean integer string if value was a float like "2091.0"
                    self.device_serial = str(int(float(sn)))
                except Exception:
                    # Fallback: just convert to string
                    self.device_serial = str(sn).strip()
            # If SN is missing, keep the previously stored serial (do not overwrite with None)

            # --- Normalize stored IP address (ensure it's clean and exact) ---
            self.device_ip = self.ip_address

            # --- Parse device metadata from raw HTML ---
            try:
                html = await async_get_raw_html(self.ip_address, self.hass)
                soup = BeautifulSoup(html, "html.parser")

                manufacturer_new = self.device_manufacturer
                model_new = self.device_model
                firmware_new = self.device_firmware

                text = soup.get_text("\n", strip=True)

                # Extract manufacturer and model from <h1> header
                header = soup.find("h1")
                if header is not None:
                    parts = [
                        line.strip()
                        for line in header.get_text("\n", strip=True).split("\n")
                        if line.strip()
                    ]
                    if len(parts) >= 2:
                        model_new = parts[0]
                        manufacturer_new = parts[1]

                # Extract metadata from legacy SOLPLUS basic menu pages.
                legacy_header = re.search(
                    r"(SOLPLUS\s+\d+),\s*S/N\s+(\d+),\s*FW-Version\s+([\d.]+)",
                    text,
                    re.IGNORECASE,
                )
                if legacy_header is not None:
                    manufacturer_new = "Solutronic"
                    model_new = " ".join(legacy_header.group(1).split()).upper()
                    self.device_serial = legacy_header.group(2)
                    firmware_new = legacy_header.group(3)

                # Extract firmware version
                for line in text.split("\n"):
                    if "FW-Release:" not in line:
                        continue

                    fw_line = line.split("FW-Release:", 1)[1].strip()
                    if fw_line:
                        firmware_new = fw_line
                    break

                # Apply parsed metadata
                self.device_manufacturer = manufacturer_new
                self.device_model = model_new
                self.device_firmware = firmware_new

                # Persist metadata so it survives inverter offline periods and HA restarts
                if self.entry is not None:
                    new_data = dict(self.entry.data)
                    new_data["manufacturer"] = self.device_manufacturer
                    new_data["model"] = self.device_model
                    new_data["firmware"] = self.device_firmware
                    new_data["serial"] = getattr(self, "device_serial", None)

                    if new_data != self.entry.data:
                        self.hass.config_entries.async_update_entry(self.entry, data=new_data)

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
            elif isinstance(data.get("PAC"), (int, float)):
                data["PAC_TOTAL"] = data["PAC"]
            else:
                data.pop("PAC_TOTAL", None)

            # --- Derived lifetime energy counter based on ET (energy today) ---
            raw_et = data.get("ET")
            et = _as_float(raw_et, None) if raw_et is not None else None
            real_total = _as_float(data.get("EG"), 0.0)
            pac = _as_float(data.get("PAC_TOTAL"), 0.0)

            # Initialize on first run after HA restart
            if self._lt_prev_et is None:
                self._lt_prev_et = et
                self._lt_total = real_total

            if et is not None and self._lt_prev_et is None:
                self._lt_prev_et = et

            if et is not None and self._lt_prev_et is not None and self._lt_total is not None:
                # --- Case 1: ET increased normally (daytime production) ---
                if et > self._lt_prev_et and pac > 0:
                    self._lt_total += (et - self._lt_prev_et)
                    self._lt_prev_et = et

                # --- Case 2: ET reset overnight (new day) ---
                elif et < self._lt_prev_et:
                    # Reset baseline but DO NOT add difference
                    self._lt_prev_et = et

                # --- Case 3: False morning start (ET rises but PAC == 0) ---
                elif et > self._lt_prev_et and pac == 0:
                    # Ignore this fake rise completely
                    self._lt_prev_et = et  # Update baseline only

                # else: no change (stable or offline)

                data["LIFETIME_DERIVED"] = round(self._lt_total, 3)

            else:
                # If ET missing, just report stored total
                data["LIFETIME_DERIVED"] = round(real_total, 3)

            # Store latest valid dataset for fallback use
            self._last_data = data
            self.supported_keys.update(key for key, value in data.items() if value is not None)
            if self._offline_logged:
                _LOGGER.info("Solutronic inverter at %s is reachable again", self.ip_address)
                self._offline_logged = False
            return data

        except Exception as err:
            # Log failure (not as error to avoid log spam)
            if not self._offline_logged:
                _LOGGER.warning(
                    "Failed to fetch data from Solutronic inverter (%s): %s",
                    self.ip_address,
                    err,
                )
                self._offline_logged = True

            # ---- Controlled fallback data behavior ----
            last = self._last_data or {}

            # Keys that should retain last known values (energy data)
            retain_keys = ["ET", "EG", "LIFETIME_DERIVED"]

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
                if key in self.supported_keys or key in last:
                    fallback[key] = 0

            # Restore ET + EG + Derived total if known
            for key in retain_keys:
                if key in self.supported_keys or key in last:
                    fallback[key] = last.get(key, 0)

            self._last_data = fallback
            return fallback

    async def async_validate_connection(self):
        """Used by config flow to verify connectivity before setup."""
        await async_get_sensor_data(self.ip_address, self.hass)
