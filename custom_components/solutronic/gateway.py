"""Isolated experimental gateway coordinator; HTTP state and IDs are untouched."""

import asyncio
import inspect
import logging
import time
from dataclasses import asdict
from datetime import timedelta

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .spp import TCP_INTERVALS, GatewayDevice, SppClient, SppError
from .util import as_energy

_LOGGER = logging.getLogger(__name__)


class GatewayCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        kwargs = (
            {"config_entry": entry}
            if "config_entry"
            in inspect.signature(DataUpdateCoordinator.__init__).parameters
            else {}
        )
        interval = entry.options.get("scan_interval", 60)
        if isinstance(interval, bool) or interval not in TCP_INTERVALS:
            interval = 60
        super().__init__(
            hass,
            _LOGGER,
            name="Solutronic gateway",
            update_interval=timedelta(seconds=interval),
            **kwargs,
        )
        self.entry = entry
        self.ip_address = entry.data["ip_address"]
        self.options = dict(entry.options)
        self.devices = [GatewayDevice(**device) for device in entry.data["devices"]]
        self.client = SppClient(
            self.ip_address,
            entry.data["master_address"],
            [d.address for d in self.devices],
        )
        self.reachable = set()
        self._latest = {}
        self._energy = {}
        self._store = Store(
            hass, 1, f"{DOMAIN}.gateway.{entry.entry_id}", atomic_writes=True
        )
        self._pending = None
        self._save_pending = False
        self._saved = None
        self.auto_discover = (
            entry.options.get(
                "discover_devices", entry.data.get("auto_discover", False)
            )
            is True
        )
        self._last_discovery = None
        self.discovery_error = None

    async def async_restore_state(self):
        try:
            state = await self._store.async_load()
        except (HomeAssistantError, OSError, ValueError):
            _LOGGER.warning("Could not restore Solutronic gateway energy state")
            return
        if not isinstance(state, dict):
            return
        for device in self.devices:
            saved = state.get(str(device.address))
            if not isinstance(saved, dict):
                continue
            energy = saved.get("energy", {})
            if not isinstance(energy, dict):
                continue
            self._energy[device.address] = {
                "total": as_energy(saved.get("total")),
                "previous_et": as_energy(saved.get("previous_et")),
            }
            self._latest[device.address] = {
                key: value
                for key in ("ET", "EG", "LIFETIME_DERIVED")
                if (value := as_energy(energy.get(key))) is not None
            }
        self._saved = self._snapshot()

    def _snapshot(self):
        return {
            str(address): {
                **state,
                "energy": {
                    key: value
                    for key in ("ET", "EG", "LIFETIME_DERIVED")
                    if (value := as_energy(self._latest.get(address, {}).get(key)))
                    is not None
                },
            }
            for address, state in self._energy.items()
        }

    def _pending_snapshot(self):
        self._save_pending = False
        self._saved = self._pending
        return self._pending

    async def async_save_state(self):
        self._pending = self._snapshot()
        try:
            await self._store.async_save(self._pending_snapshot())
        except (HomeAssistantError, OSError, ValueError):
            _LOGGER.warning("Could not save Solutronic gateway energy state")

    def _accept_readings(self, address, values):
        values = dict(values)
        state = self._energy.setdefault(address, {"total": None, "previous_et": None})
        et, eg = as_energy(values.get("ET")), as_energy(values.get("EG"))
        if state["total"] is None and eg is not None:
            state["total"] = eg
            state["previous_et"] = et
        previous = state["previous_et"]
        if et is not None:
            if previous is not None and state["total"] is not None:
                if et > previous and values.get("PAC_TOTAL", 0) > 0:
                    state["total"] += et - previous
            state["previous_et"] = et
        if state["total"] is not None:
            values["LIFETIME_DERIVED"] = round(state["total"], 3)
        self._latest[address] = values

    async def _async_update_data(self):
        if self.auto_discover and (
            self._last_discovery is None
            or time.monotonic() - self._last_discovery >= 600
        ):
            self._last_discovery = time.monotonic()
            try:
                addresses = await self.client.async_discover()
            except (OSError, TimeoutError, asyncio.IncompleteReadError, SppError):
                self.discovery_error = "discovery_failed"
                # Keep the last verified list during a transient discovery outage.
            else:
                self.discovery_error = None
                known = {device.address for device in self.devices}
                self.devices.extend(
                    GatewayDevice(address, None)
                    for address in addresses
                    if address not in known
                )
                self.client.addresses = tuple(addresses)
                new_data = dict(self.entry.data)
                new_data["devices"] = [asdict(device) for device in self.devices]
                if new_data != self.entry.data:
                    self.hass.config_entries.async_update_entry(
                        self.entry, data=new_data
                    )
        results = await self.client.async_poll()
        self.reachable = {
            address for address, values in results.items() if values is not None
        }
        for address in self.reachable:
            self._accept_readings(address, results[address])
        if not self.reachable:
            raise UpdateFailed("No configured gateway inverter returned valid readings")
        self._pending = self._snapshot()
        if not self._save_pending and self._pending != self._saved:
            self._save_pending = True
            self._store.async_delay_save(self._pending_snapshot, 60)
        return dict(self._latest)

    async def async_shutdown(self):
        await self.client.async_shutdown()
        await super().async_shutdown()
