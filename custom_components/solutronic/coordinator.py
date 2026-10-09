import inspect
import logging
import re
from datetime import timedelta

from bs4 import BeautifulSoup
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import DOMAIN, KEY_LIFETIME_DERIVED
from .solutronic_api import async_get_sensor_snapshot, get_cached_base_url
from .util import as_energy, as_float

_LOGGER = logging.getLogger(__name__)
_ENERGY_KEYS = ("ET", "EG", KEY_LIFETIME_DERIVED)
_STORAGE_SAVE_DELAY = 60
_SUPPORTS_CONFIG_ENTRY = (
    "config_entry" in inspect.signature(DataUpdateCoordinator.__init__).parameters
)


class SolutronicDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator that polls the Solutronic inverter and provides stable data."""

    def __init__(self, hass, ip_address, scan_interval, entry=None):
        # Prefer the explicit entry API while retaining support for older HA
        # versions, where the coordinator obtains it from the setup context.
        entry_kwargs = {"config_entry": entry} if _SUPPORTS_CONFIG_ENTRY else {}
        # Initialize coordinator with dynamic polling interval
        super().__init__(
            hass,
            _LOGGER,
            name="Solutronic",
            update_interval=timedelta(seconds=scan_interval),
            **entry_kwargs,
        )

        self.ip_address = ip_address
        self.hass = hass
        self.entry = entry
        self.options = dict(entry.options) if entry is not None else {}
        self._last_data = None  # Store last known valid data for fallback
        self.supported_keys = set()

        # Lifetime counter internal state
        self._lt_prev_et = None
        self._lt_total = None
        self._store = (
            Store(hass, 1, f"{DOMAIN}.{entry.entry_id}", atomic_writes=True)
            if entry is not None
            else None
        )
        self._storage_pending = False
        self._storage_snapshot = None
        self._pending_state = None

        self._offline_logged = False
        self.last_successful_update = None
        self.last_error_type = None
        self.consecutive_failures = 0
        self.device_url = f"http://{ip_address}/"

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

    def _state_to_store(self):
        """Snapshot only energy and supported keys, never instantaneous readings."""
        return {
            "total": self._lt_total,
            "previous_et": self._lt_prev_et,
            "supported_keys": sorted(self.supported_keys),
            "energy": {
                key: value
                for key in _ENERGY_KEYS
                if (value := as_energy((self._last_data or {}).get(key))) is not None
            },
        }

    async def async_restore_state(self):
        """Restore energy state before polling, including when starting offline."""
        if self._store is None:
            return
        try:
            state = await self._store.async_load()
        except (HomeAssistantError, OSError, ValueError):
            _LOGGER.warning("Could not restore Solutronic energy state", exc_info=True)
            return
        if not isinstance(state, dict):
            return
        self._lt_total = as_energy(state.get("total"))
        self._lt_prev_et = as_energy(state.get("previous_et"))
        keys = state.get("supported_keys")
        if isinstance(keys, list):
            self.supported_keys.update(key for key in keys if isinstance(key, str))
        energy = state.get("energy")
        if isinstance(energy, dict):
            self._last_data = {
                key: value
                for key in _ENERGY_KEYS
                if (value := as_energy(energy.get(key))) is not None
            }
        self._storage_snapshot = self._state_to_store()

    def _async_pending_state(self):
        """Return a snapshot safe for older HA's storage worker thread."""
        state = self._pending_state
        self._storage_pending = False
        self._storage_snapshot = state
        return state

    def _schedule_save(self):
        """Coalesce changes without postponing a save on every poll."""
        if self._store is None:
            return
        # Build a new snapshot in the event loop; never iterate live coordinator
        # data in the save callback, which older HA runs in an executor thread.
        self._pending_state = self._state_to_store()
        if not self._storage_pending and self._pending_state != self._storage_snapshot:
            self._storage_pending = True
            self._store.async_delay_save(self._async_pending_state, _STORAGE_SAVE_DELAY)

    async def async_save_state(self):
        """Flush energy before an integration reload."""
        if self._store is not None:
            try:
                self._pending_state = self._state_to_store()
                await self._store.async_save(self._async_pending_state())
            except (HomeAssistantError, OSError, ValueError):
                _LOGGER.warning("Could not save Solutronic energy state", exc_info=True)

    async def _async_update_data(self):
        """Fetch data and return fallback data if device is temporarily unreachable."""
        try:
            # Request data from the inverter (parsed sensor values)
            data, html = await async_get_sensor_snapshot(self.ip_address, self.hass)
            self.device_url = get_cached_base_url(self.ip_address) or self.device_url

            # --- Extract serial number (SN) and ensure no decimal formatting ---
            sn = data.get("SN")
            if sn is not None:
                try:
                    # Convert to clean integer string if value was a float like "2091.0"
                    self.device_serial = str(int(float(sn)))
                except (TypeError, ValueError, OverflowError):
                    # Fallback: just convert to string
                    self.device_serial = str(sn).strip()
            # Keep the previously stored serial when SN is missing.

            # --- Normalize stored IP address (ensure it's clean and exact) ---
            self.device_ip = self.ip_address

            # --- Parse device metadata from raw HTML ---
            try:
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

                # Persist metadata across outages and HA restarts.
                if self.entry is not None:
                    new_data = dict(self.entry.data)
                    new_data["manufacturer"] = self.device_manufacturer
                    new_data["model"] = self.device_model
                    new_data["firmware"] = self.device_firmware
                    new_data["serial"] = getattr(self, "device_serial", None)

                    if new_data != self.entry.data:
                        self.hass.config_entries.async_update_entry(
                            self.entry, data=new_data
                        )

            except Exception:
                # Metadata parsing errors should never stop telemetry updates
                _LOGGER.debug("Could not parse Solutronic metadata", exc_info=True)

            # --- Fail-safe total AC power calculation (PAC_TOTAL) ---
            phase_keys = {"PACL1", "PACL2", "PACL3"} & (self.supported_keys | set(data))
            pac_values = [as_float(data.get(key)) for key in phase_keys]
            if pac_values and all(value is not None for value in pac_values):
                data["PAC_TOTAL"] = sum(pac_values)
            elif (total_power := as_float(data.get("PAC"))) is not None:
                data["PAC_TOTAL"] = total_power
            else:
                data.pop("PAC_TOTAL", None)

            # --- Derived lifetime energy counter based on ET (energy today) ---
            raw_et = data.get("ET")
            et = as_energy(raw_et)
            real_total = as_energy(data.get("EG"))
            pac = as_float(data.get("PAC_TOTAL"), 0.0)

            # Existing installations without stored state still start from EG.
            if self._lt_total is None and real_total is not None:
                self._lt_total = real_total
                self._lt_prev_et = et

            if et is not None and self._lt_prev_et is None:
                self._lt_prev_et = et

            if (
                et is not None
                and self._lt_prev_et is not None
                and self._lt_total is not None
            ):
                # --- Case 1: ET increased normally (daytime production) ---
                if et > self._lt_prev_et and pac > 0:
                    self._lt_total += et - self._lt_prev_et
                    self._lt_prev_et = et

                # --- Case 2: ET reset overnight (new day) ---
                elif et < self._lt_prev_et:
                    # Reset baseline but DO NOT add difference
                    self._lt_prev_et = et

                # --- Case 3: False morning start (ET rises but PAC == 0) ---
                elif et > self._lt_prev_et and data.get("PAC_TOTAL") == 0:
                    # Ignore this fake rise completely
                    self._lt_prev_et = et  # Update baseline only

                # else: no change (stable or offline)

            if self._lt_total is not None:
                # Missing ET must not reset an already established counter.
                data[KEY_LIFETIME_DERIVED] = round(self._lt_total, 3)

            # Partial responses must not discard known energy. The calculation
            # above uses only fresh ET, so retained readings cannot be counted twice.
            for key in _ENERGY_KEYS:
                if as_energy(data.get(key)) is None:
                    value = as_energy((self._last_data or {}).get(key))
                    if value is not None:
                        data[key] = value

            # Store latest valid dataset for fallback use
            self._last_data = data
            self.supported_keys.update(
                key for key, value in data.items() if value is not None
            )
            self._schedule_save()
            self.last_successful_update = dt_util.utcnow()
            self.last_error_type = None
            self.consecutive_failures = 0
            if self._offline_logged:
                _LOGGER.info(
                    "Solutronic inverter at %s is reachable again", self.ip_address
                )
                self._offline_logged = False
            return data

        except Exception as err:
            self.last_error_type = type(err).__name__
            self.consecutive_failures += 1
            # Log failure (not as error to avoid log spam)
            if not self._offline_logged:
                _LOGGER.debug("Solutronic update failed", exc_info=True)
                _LOGGER.warning(
                    "Failed to fetch data from Solutronic inverter (%s): %s",
                    self.ip_address,
                    str(err) or self.last_error_type,
                )
                self._offline_logged = True

            # ---- Controlled fallback data behavior ----
            last = self._last_data or {}

            # Keys that should retain last known values (energy data)
            retain_keys = _ENERGY_KEYS

            # Keys that should be zero when inverter is offline
            zero_keys = [
                "PAC",
                "PAC_TOTAL",
                "PACL1",
                "PACL2",
                "PACL3",
                "UDC1",
                "UDC2",
                "UDC3",
                "IDC1",
                "IDC2",
                "IDC3",
                "IAC1",
                "MAXP",
                "ETA",
                "UACL1",
                "UACL2",
                "UACL3",
            ]

            fallback = {}

            # Set zero-values for momentary readings
            for key in zero_keys:
                if key in self.supported_keys or key in last:
                    fallback[key] = 0

            # Restore ET + EG + Derived total if known
            for key in retain_keys:
                if key in last:
                    fallback[key] = last[key]

            self._last_data = fallback
            return fallback
