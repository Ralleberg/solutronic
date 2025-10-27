import logging
from datetime import timedelta

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from .solutronic_api import async_get_sensor_data, async_get_raw_html, async_get_mac
from .discovery import discover_solutronic  # used for auto-reconnect scan

_LOGGER = logging.getLogger(__name__)


class SolutronicDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator that polls the Solutronic inverter and provides stable data."""

    def __init__(self, hass, ip_address, scan_interval):
        super().__init__(
            hass,
            _LOGGER,
            name="Solutronic",
            update_interval=timedelta(seconds=scan_interval),
        )

        self.hass = hass
        self.ip_address = ip_address
        self._last_data = None

        # Lifetime counter internal state
        self._lt_prev_et = None
        self._lt_total = None

        self._bridge_warning_logged = False

        # Load stored metadata if available
        entry = next(
            (entry for entry in self.hass.config_entries.async_entries() if entry.data.get("ip_address") == self.ip_address),
            None
        )

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
        try:
            data = await async_get_sensor_data(self.ip_address)

            # --- Extract serial number safely ---
            sn = data.get("SN")
            if sn is not None:
                try:
                    new_serial = str(int(float(sn)))
                except Exception:
                    new_serial = str(sn).strip()
            else:
                new_serial = self.device_serial

            self.device_serial = new_serial

            # --- Retrieve metadata if reachable ---
            try:
                html = await async_get_raw_html(self.ip_address)

                if "<h1>" in html:
                    header = html.split("<h1>")[1].split("</h1>")[0]
                    parts = [line.strip() for line in header.replace("<br>", "\n").split("\n") if line.strip()]
                    if len(parts) >= 2:
                        self.device_model = parts[0]
                        self.device_manufacturer = parts[1]

                if "FW-Release" in html:
                    fw_line = html.split("FW-Release:")[1].split("<")[0].strip()
                    self.device_firmware = fw_line

                # ✅ Persist metadata correctly
                entry = next(
                    (entry for entry in self.hass.config_entries.async_entries() if entry.data.get("ip_address") == self.ip_address),
                    None
                )
                if entry:
                    new_data = dict(entry.data)
                    new_data["ip_address"] = self.ip_address
                    new_data["manufacturer"] = self.device_manufacturer
                    new_data["model"] = self.device_model
                    new_data["firmware"] = self.device_firmware
                    new_data["serial"] = self.device_serial
                    entry.async_update_entry(data=new_data)

            except Exception:
                pass

            # --- Recalculate PAC_TOTAL ---
            pac_values = [v for k, v in data.items() if k.startswith("PACL") and isinstance(v, (int, float))]
            data["PAC_TOTAL"] = sum(pac_values) if pac_values else 0

            # --- Lifetime Derived Energy ---
            et = data.get("ET")
            real_total = float(data.get("EG", 0) or 0)
            pac = data.get("PAC_TOTAL", 0) or 0

            if self._lt_prev_et is None:
                self._lt_prev_et = et
                self._lt_total = real_total

            if et is not None:
                if et > self._lt_prev_et and pac > 0:
                    self._lt_total += (et - self._lt_prev_et)
                    self._lt_prev_et = et
                elif et < self._lt_prev_et:
                    self._lt_prev_et = et
                elif et > self._lt_prev_et and pac == 0:
                    self._lt_prev_et = et

                data["LIFETIME_DERIVED"] = round(self._lt_total, 3)
            else:
                data["LIFETIME_DERIVED"] = round(self._lt_total, 3)

            self._last_data = data
            return data

        except Exception as err:
            _LOGGER.warning("Failed to fetch data from Solutronic inverter (%s): %s", self.ip_address, err)

            last = self._last_data or {}
            fallback = {k: 0 for k in ["PAC", "PAC_TOTAL", "PACL1", "PACL2", "PACL3", "UDC1", "UDC2", "UDC3", "IDC1", "IDC2", "IDC3", "MAXP", "ETA", "UACL1", "UACL2", "UACL3"]}
            for key in ["ET", "EG", "LIFETIME_DERIVED"]:
                fallback[key] = last.get(key, 0)

            self._last_data = fallback
            return fallback

    async def async_validate_connection(self):
        await async_get_sensor_data(self.ip_address)