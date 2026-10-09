"""Regression tests using real Home Assistant helpers and mocked inverter replies."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
from homeassistant.config_entries import ConfigEntryState, current_entry
from homeassistant.const import EVENT_HOMEASSISTANT_FINAL_WRITE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import frame

from custom_components.solutronic import (
    async_reload_entry,
    async_unload_entry,
)
from custom_components.solutronic import (
    async_setup_entry as async_setup_integration,
)
from custom_components.solutronic import solutronic_api as api
from custom_components.solutronic.config_flow import (
    SolutronicInverterConfigFlow,
    SolutronicInverterOptionsFlow,
)
from custom_components.solutronic.const import DOMAIN
from custom_components.solutronic.coordinator import SolutronicDataUpdateCoordinator
from custom_components.solutronic.diagnostics import async_get_config_entry_diagnostics
from custom_components.solutronic.sensor import SENSORS, async_setup_entry
from custom_components.solutronic.util import scan_interval

TABLE_HTML = """<h1>SOLPLUS 100<br>Solutronic</h1><p>FW-Release: 3.0</p>
<table><tr><td>Power</td><td>PACL1</td><td>W</td><td>1250</td></tr>
<tr><td>Energy today</td><td>ET</td><td>kWh</td><td>2,5</td></tr>
<tr><td>Energy total</td><td>EG</td><td>kWh</td><td>1000</td></tr>
<tr><td>Serial</td><td>SN</td><td></td><td>2091</td></tr></table>"""
LEGACY_HTML = """<h1>Webserver for SOLPLUS</h1><p>
SOLPLUS 25, S/N 2091, FW-Version 2.53<br>
power AC: 1250 W<br>mains voltage: 230 V<br>mains current: 5,4 A<br>
DC voltage: 300 V<br>DC-current: 4,5 A<br>energy today: 2,5 kWh<br>
energy total: 1000 kWh<br>efficiency: 92 %<br>maximum power today: 1500 W
</p>"""


class StabilityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.hass = HomeAssistant(self.directory.name)
        if hasattr(frame, "async_setup"):
            frame.async_setup(self.hass)
        self.entry = SimpleNamespace(
            entry_id="existing_entry",
            data={"ip_address": "192.0.2.1"},
            options={},
            title="Solutronic",
            domain=DOMAIN,
            async_on_unload=Mock(),
            pref_disable_polling=False,
            state=ConfigEntryState.SETUP_IN_PROGRESS,
        )
        self.hass.config_entries = SimpleNamespace(
            async_update_entry=Mock(
                side_effect=lambda entry, data: setattr(entry, "data", data)
            ),
            async_reload=AsyncMock(return_value=True),
            async_unload_platforms=AsyncMock(return_value=True),
        )
        self.coordinator = self.make_coordinator()
        api._BASE_URL_CACHE.clear()

    async def asyncTearDown(self):
        # Store writes cancel delayed saves, and coordinator shutdown cancels its
        # debouncer. No real inverter or running HA installation is involved.
        await self.coordinator.async_save_state()
        await self.coordinator.async_shutdown()
        await self.hass.async_block_till_done()

    def make_coordinator(self):
        return SolutronicDataUpdateCoordinator(self.hass, "192.0.2.1", 5, self.entry)

    async def poll(self, values=None, error=None, coordinator=None, html=TABLE_HTML):
        target = coordinator or self.coordinator
        snapshot = (
            AsyncMock(side_effect=error)
            if error
            else AsyncMock(return_value=(dict(values), html))
        )
        with patch(
            "custom_components.solutronic.coordinator.async_get_sensor_snapshot",
            snapshot,
        ):
            target.data = await target._async_update_data()
        return target.data

    async def test_first_upgrade_keeps_existing_energy_baseline(self):
        await self.coordinator.async_restore_state()
        data = await self.poll({"PACL1": 100, "ET": 5, "EG": 1000})
        self.assertEqual(data["LIFETIME_DERIVED"], 1000)
        self.assertEqual(data["PAC_TOTAL"], 100)

    async def test_integration_setup_restores_before_first_refresh(self):
        await self.poll({"PAC": 100, "ET": 5, "EG": 1000})
        await self.poll({"PAC": 100, "ET": 7, "EG": 1000})
        await self.coordinator.async_save_state()
        self.entry.state = ConfigEntryState.SETUP_IN_PROGRESS
        self.entry.async_on_unload = Mock()
        self.entry.add_update_listener = Mock()
        self.entry.pref_disable_polling = False
        self.hass.config_entries.async_forward_entry_setups = AsyncMock()
        token = current_entry.set(self.entry)
        try:
            with patch(
                "custom_components.solutronic.coordinator.async_get_sensor_snapshot",
                return_value=({"PAC": 100, "ET": 8, "EG": 1000}, TABLE_HTML),
            ):
                self.assertTrue(await async_setup_integration(self.hass, self.entry))
            active = self.hass.data[DOMAIN][self.entry.entry_id]
            self.assertEqual(active.data["LIFETIME_DERIVED"], 1003)
            self.hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(
                self.entry, ["sensor"]
            )
            await active.async_save_state()
            await active.async_shutdown()
        finally:
            current_entry.reset(token)

    async def test_restart_restores_derived_total_even_if_eg_is_stale(self):
        await self.poll({"PAC": 100, "ET": 5, "EG": 1000})
        await self.poll({"PAC": 100, "ET": 7, "EG": 1000})
        await self.coordinator.async_save_state()
        restarted = self.make_coordinator()
        try:
            await restarted.async_restore_state()
            result = await self.poll(
                {"PAC": 100, "ET": 8, "EG": 1000}, coordinator=restarted
            )
            self.assertEqual(result["LIFETIME_DERIVED"], 1003)
        finally:
            await restarted.async_save_state()
            await restarted.async_shutdown()

    async def test_daily_reset_does_not_reduce_or_spike_total(self):
        await self.poll({"PAC": 100, "ET": 5, "EG": 1000})
        await self.poll({"PAC": 100, "ET": 7, "EG": 1000})
        data = await self.poll({"PAC": 0, "ET": 0, "EG": 1002})
        self.assertEqual(data["LIFETIME_DERIVED"], 1002)
        data = await self.poll({"PAC": 100, "ET": 0.5, "EG": 1002})
        self.assertEqual(data["LIFETIME_DERIVED"], 1002.5)

    async def test_missing_et_does_not_reset_counter_or_baseline(self):
        await self.poll({"PAC": 100, "ET": 5, "EG": 1000})
        await self.poll({"PAC": 100, "ET": 7, "EG": 1000})
        self.assertEqual(
            (await self.poll({"PAC": 100, "EG": 1000}))["LIFETIME_DERIVED"], 1002
        )
        self.assertEqual(
            (await self.poll({"PAC": 100, "ET": 8, "EG": 1000}))["LIFETIME_DERIVED"],
            1003,
        )

    async def test_initial_missing_et_does_not_reinitialize_from_stale_eg(self):
        await self.poll({"PAC": 100, "EG": 1000})
        data = await self.poll({"PAC": 100, "ET": 5, "EG": 999})
        self.assertEqual(data["LIFETIME_DERIVED"], 1000)

    async def test_unknown_eg_does_not_invent_zero_energy(self):
        data = await self.poll({"PAC": 100, "ET": 5})
        self.assertNotIn("LIFETIME_DERIVED", data)

    async def test_zero_power_morning_rise_keeps_previous_behavior(self):
        await self.poll({"PAC": 0, "ET": 0, "EG": 1000})
        data = await self.poll({"PAC": 0, "ET": 1, "EG": 1000})
        self.assertEqual(data["LIFETIME_DERIVED"], 1000)
        data = await self.poll({"PAC": 100, "ET": 2, "EG": 1000})
        self.assertEqual(data["LIFETIME_DERIVED"], 1001)

    async def test_outage_retains_energy_and_existing_zero_fallback(self):
        await self.poll({"PACL1": 100, "UACL1": 230, "ET": 5, "EG": 1000})
        for _ in range(2):
            data = await self.poll(error=TimeoutError())
            self.assertEqual(data["PAC_TOTAL"], 0)
            self.assertEqual(data["UACL1"], 0)
            self.assertEqual(data["ET"], 5)
            self.assertEqual(data["LIFETIME_DERIVED"], 1000)
            self.assertNotIn("PACL2", data)
        data = await self.poll({"PACL1": 100, "ET": 6, "EG": 1000})
        self.assertEqual(data["LIFETIME_DERIVED"], 1001)
        self.assertFalse(self.coordinator._offline_logged)

    async def test_offline_restart_keeps_model_keys_and_sensor_ids(self):
        await self.poll({"PACL1": 100, "IAC1": 5, "ET": 5, "EG": 1000})
        await self.coordinator.async_save_state()
        restarted = self.make_coordinator()
        try:
            await restarted.async_restore_state()
            await self.poll(error=TimeoutError(), coordinator=restarted)
            self.hass.data[DOMAIN] = {self.entry.entry_id: restarted}
            entities = []
            await async_setup_entry(self.hass, self.entry, entities.extend)
            self.assertIn(
                "existing_entry_IAC1", {entity.unique_id for entity in entities}
            )
            self.assertNotIn(
                "existing_entry_PACL2", {entity.unique_id for entity in entities}
            )
            self.assertEqual(restarted.data["LIFETIME_DERIVED"], 1000)
        finally:
            await restarted.async_save_state()
            await restarted.async_shutdown()

    async def test_partial_response_does_not_drop_existing_entities_on_restart(self):
        await self.poll({"PACL1": 100, "UACL1": 230, "ET": 5, "EG": 1000})
        await self.poll({"PACL1": 100, "ET": 6, "EG": 1000})
        self.hass.data[DOMAIN] = {self.entry.entry_id: self.coordinator}
        entities = []
        await async_setup_entry(self.hass, self.entry, entities.extend)
        self.assertIn("existing_entry_UACL1", {entity.unique_id for entity in entities})

    async def test_no_history_offline_preserves_broad_entity_setup(self):
        await self.poll(error=TimeoutError())
        self.hass.data[DOMAIN] = {self.entry.entry_id: self.coordinator}
        entities = []
        await async_setup_entry(self.hass, self.entry, entities.extend)
        self.assertEqual(len(entities), len(SENSORS))

    async def test_storage_changes_are_coalesced_and_not_postponed(self):
        with patch.object(
            self.coordinator._store,
            "async_delay_save",
            wraps=self.coordinator._store.async_delay_save,
        ) as save:
            for value in range(5, 10):
                await self.poll({"PAC": 100, "ET": value, "EG": 1000})
            self.assertEqual(save.call_count, 1)
        await self.coordinator.async_save_state()
        stored = json.loads(
            Path(
                self.directory.name, ".storage", "solutronic.existing_entry"
            ).read_text()
        )["data"]
        self.assertEqual(stored["total"], 1004)
        self.assertNotIn("PAC", stored["energy"])

    async def test_scheduled_storage_write_saves_latest_snapshot(self):
        with patch("custom_components.solutronic.coordinator._STORAGE_SAVE_DELAY", 0):
            await self.poll({"PAC": 100, "ET": 5, "EG": 1000})
            await self.poll({"PAC": 100, "ET": 7, "EG": 1000})
        # Let the actual HA Store timer and its executor write run.
        await asyncio.sleep(0)
        await self.hass.async_block_till_done()
        stored = await self.coordinator._store.async_load()
        self.assertEqual(stored["total"], 1002)
        self.assertFalse(self.coordinator._storage_pending)

    async def test_final_write_flushes_pending_energy(self):
        await self.poll({"PAC": 100, "ET": 5, "EG": 1000})
        await self.poll({"PAC": 100, "ET": 7, "EG": 1000})
        self.hass.bus.async_fire(EVENT_HOMEASSISTANT_FINAL_WRITE)
        await self.hass.async_block_till_done()
        stored = await self.coordinator._store.async_load()
        self.assertEqual(stored["total"], 1002)

    async def test_unreadable_storage_does_not_prevent_polling(self):
        with patch.object(
            self.coordinator._store, "async_load", side_effect=OSError("unreadable")
        ):
            await self.coordinator.async_restore_state()
        self.assertEqual(
            (await self.poll({"PAC": 100, "ET": 5, "EG": 1000}))["LIFETIME_DERIVED"],
            1000,
        )

    async def test_malformed_storage_ignores_invalid_fields(self):
        with patch.object(
            self.coordinator._store,
            "async_load",
            return_value={
                "total": "nan",
                "previous_et": "inf",
                "supported_keys": [None, [], "PACL1"],
                "energy": {"ET": "invalid"},
            },
        ):
            await self.coordinator.async_restore_state()
        self.assertEqual(
            (await self.poll({"PAC": 100, "ET": 5, "EG": 1000}))["LIFETIME_DERIVED"],
            1000,
        )

    async def test_metadata_updates_do_not_reload(self):
        self.hass.data[DOMAIN] = {self.entry.entry_id: self.coordinator}
        await self.poll({"PAC": 100, "ET": 5, "EG": 1000})
        await async_reload_entry(self.hass, self.entry)
        self.hass.config_entries.async_reload.assert_not_awaited()

    async def test_options_change_uses_ha_managed_reload(self):
        self.hass.data[DOMAIN] = {self.entry.entry_id: self.coordinator}
        self.entry.options = {"scan_interval": 30}
        await async_reload_entry(self.hass, self.entry)
        self.hass.config_entries.async_reload.assert_awaited_once_with(
            self.entry.entry_id
        )

    async def test_failed_unload_does_not_remove_coordinator(self):
        self.hass.data[DOMAIN] = {self.entry.entry_id: self.coordinator}
        self.hass.config_entries.async_unload_platforms.return_value = False
        self.assertFalse(await async_unload_entry(self.hass, self.entry))
        self.assertIs(self.hass.data[DOMAIN][self.entry.entry_id], self.coordinator)

    async def test_successful_unload_flushes_latest_energy(self):
        self.hass.data[DOMAIN] = {self.entry.entry_id: self.coordinator}
        await self.poll({"PAC": 100, "ET": 5, "EG": 1000})
        await self.poll({"PAC": 100, "ET": 6, "EG": 1000})
        self.assertTrue(await async_unload_entry(self.hass, self.entry))
        stored = await self.coordinator._store.async_load()
        self.assertEqual(stored["total"], 1001)

    async def test_options_flow_works_with_read_only_config_entry(self):
        self.entry.options = {"scan_interval": 30}
        flow = SolutronicInverterOptionsFlow(self.entry)
        result = await flow.async_step_init()
        self.assertEqual(result["data_schema"]({})["scan_interval"], 30)
        result = await flow.async_step_init({"scan_interval": 10})
        self.assertEqual(result["data"], {"scan_interval": 10})

    async def test_single_response_supplies_telemetry_and_metadata(self):
        with (
            patch.object(api, "async_get_clientsession", return_value=object()),
            patch.object(
                api,
                "_probe_working_base",
                return_value="http://192.0.2.1:8888/solutronic/",
            ),
            patch.object(api, "_fetch_text", return_value=TABLE_HTML) as fetch,
        ):
            data, html = await api.async_get_sensor_snapshot("192.0.2.1", self.hass)
            self.assertEqual(fetch.await_count, 1)
            self.assertEqual(data["ET"], 2.5)
            await self.poll(data, html=html)
            self.assertEqual(self.coordinator.device_model, "SOLPLUS 100")
            self.assertEqual(self.coordinator.device_serial, "2091")
            self.assertEqual(self.coordinator.device_firmware, "3.0")

    async def test_stale_endpoint_retries_once_and_reprobes(self):
        old = "http://192.0.2.1:8888/solutronic/"
        new = "http://192.0.2.1:80/"
        api._BASE_URL_CACHE["192.0.2.1"] = old
        with (
            patch.object(api, "async_get_clientsession", return_value=object()),
            patch.object(api, "_probe_working_base", side_effect=[old, new]) as probe,
            patch.object(
                api,
                "_fetch_text",
                side_effect=[aiohttp.ClientConnectionError(), TABLE_HTML],
            ) as fetch,
        ):
            data = await api.async_get_sensor_data("192.0.2.1", self.hass)
            self.assertEqual(data["ET"], 2.5)
            self.assertEqual(probe.await_count, 2)
            self.assertEqual(fetch.await_count, 2)
            self.assertNotIn("192.0.2.1", api._BASE_URL_CACHE)

    async def test_normal_polling_uses_one_http_request_after_discovery(self):
        base = "http://192.0.2.1:8888/solutronic/"
        api._BASE_URL_CACHE["192.0.2.1"] = base
        with (
            patch.object(api, "async_get_clientsession", return_value=object()),
            patch.object(api, "_fetch_text", return_value=TABLE_HTML) as fetch,
        ):
            for _ in range(3):
                await self.coordinator._async_update_data()
            self.assertEqual(fetch.await_count, 3)

    async def test_retry_exhaustion_returns_coordinator_fallback(self):
        await self.poll({"PAC": 100, "ET": 5, "EG": 1000})
        with (
            patch.object(api, "async_get_clientsession", return_value=object()),
            patch.object(api, "_probe_working_base", return_value="http://192.0.2.1/"),
            patch.object(api, "_fetch_text", side_effect=asyncio.TimeoutError()),
        ):
            data = await self.coordinator._async_update_data()
        self.assertEqual(data["PAC_TOTAL"], 0)
        self.assertEqual(data["LIFETIME_DERIVED"], 1000)

    async def test_non_telemetry_response_is_rejected(self):
        with patch.object(
            api, "async_get_raw_html", return_value="<p>Unrelated page</p>"
        ):
            with self.assertRaises(api.SolutronicInvalidResponseError):
                await api.async_get_sensor_data("192.0.2.1", self.hass)

    async def test_legacy_parser_and_metadata_are_preserved(self):
        data = api._parse_sensor_data(LEGACY_HTML)
        self.assertEqual(data["IAC1"], 5.4)
        self.assertEqual(data["PACL1"], 1250)
        self.assertNotIn("PACL2", data)
        result = await self.poll(data, html=LEGACY_HTML)
        self.assertEqual(result["PAC_TOTAL"], 1250)
        self.assertEqual(self.coordinator.device_model, "SOLPLUS 25")
        self.assertEqual(self.coordinator.device_firmware, "2.53")

    async def test_partial_phase_data_does_not_publish_incomplete_total(self):
        await self.poll({"PACL1": 100, "PACL2": 200, "PACL3": 300, "ET": 5, "EG": 1000})
        data = await self.poll({"PACL1": 100, "PACL2": 200, "ET": 6, "EG": 1000})
        self.assertNotIn("PAC_TOTAL", data)
        # Unknown power does not consume this increase as a false zero-power rise.
        data = await self.poll(
            {"PACL1": 100, "PACL2": 200, "PACL3": 300, "ET": 7, "EG": 1000}
        )
        self.assertEqual(data["LIFETIME_DERIVED"], 1002)

    async def test_partial_phase_data_can_use_reported_total_power(self):
        await self.poll({"PACL1": 100, "PACL2": 200, "PACL3": 300})
        data = await self.poll({"PACL1": 100, "PACL2": None, "PAC": 600})
        self.assertEqual(data["PAC_TOTAL"], 600)

    async def test_partial_response_retains_energy_for_later_outage(self):
        await self.poll({"PAC": 100, "ET": 5, "EG": 1000})
        await self.poll({"PAC": 100, "ET": None, "EG": None})
        data = await self.poll(error=TimeoutError())
        self.assertEqual(data["ET"], 5)
        self.assertEqual(data["EG"], 1000)
        self.assertEqual(data["LIFETIME_DERIVED"], 1000)

    async def test_invalid_telemetry_does_not_reach_numeric_sensors(self):
        for value in ("", "n/a", "NaN", "Infinity", "-Infinity"):
            with (
                self.subTest(value=value),
                patch.object(
                    api,
                    "async_get_raw_html",
                    return_value=TABLE_HTML.replace("1250", value),
                ),
            ):
                data = await api.async_get_sensor_data("192.0.2.1", self.hass)
                self.assertIsNone(data["PACL1"])
                self.assertEqual(data["ET"], 2.5)

    async def test_response_with_only_invalid_telemetry_is_rejected(self):
        html = (
            "<table><tr><td>Power</td><td>PACL1</td><td>W</td><td>NaN</td></tr></table>"
        )
        with patch.object(api, "async_get_raw_html", return_value=html):
            with self.assertRaises(api.SolutronicInvalidResponseError):
                await api.async_get_sensor_data("192.0.2.1", self.hass)

    async def test_negative_energy_readings_are_ignored(self):
        with patch.object(
            api, "async_get_raw_html", return_value=TABLE_HTML.replace("2,5", "-1")
        ):
            data = await api.async_get_sensor_data("192.0.2.1", self.hass)
        self.assertIsNone(data["ET"])
        self.assertEqual(data["EG"], 1000)

    async def test_sensor_device_link_uses_discovered_endpoint(self):
        base = "http://192.0.2.1:8888/solutronic/"
        api._BASE_URL_CACHE["192.0.2.1"] = base
        await self.poll({"PACL1": 100, "SN": 2091})
        self.hass.data[DOMAIN] = {self.entry.entry_id: self.coordinator}
        entities = []
        await async_setup_entry(self.hass, self.entry, entities.extend)
        self.assertEqual(entities[0].device_info["configuration_url"], base)
        self.assertEqual(entities[0].device_info["serial_number"], "2091")
        self.assertEqual(
            entities[0].device_info["identifiers"], {(DOMAIN, self.entry.entry_id)}
        )

    async def test_diagnostics_redacts_identifiers_and_tracks_outages(self):
        self.hass.data[DOMAIN] = {self.entry.entry_id: self.coordinator}
        await self.poll({"PAC": 100, "ET": 5, "EG": 1000, "SN": 2091})
        result = await async_get_config_entry_diagnostics(self.hass, self.entry)
        self.assertTrue(result["connection"]["reachable"])
        await self.poll(error=TimeoutError())
        await self.poll(error=TimeoutError())
        result = await async_get_config_entry_diagnostics(self.hass, self.entry)
        self.assertEqual(result["connection"]["consecutive_failures"], 2)
        self.assertEqual(result["connection"]["last_error_type"], "TimeoutError")
        self.assertFalse(result["connection"]["reachable"])
        serialized = json.dumps(result, allow_nan=False)
        self.assertNotIn("192.0.2.1", serialized)
        self.assertNotIn("2091", serialized)
        self.assertNotIn("SN", result["sensor_data"])

    async def test_diagnostics_works_for_unloaded_entry(self):
        result = await async_get_config_entry_diagnostics(self.hass, self.entry)
        self.assertIn("configuration", result)
        self.assertNotIn("192.0.2.1", json.dumps(result))

    async def test_options_keep_unrelated_settings_and_reject_invalid_interval(self):
        self.entry.options = {"scan_interval": 30, "future_option": True}
        flow = SolutronicInverterOptionsFlow(self.entry)
        result = await flow.async_step_init({"scan_interval": 0})
        self.assertEqual(result["errors"]["scan_interval"], "invalid_interval")
        result = await flow.async_step_init({"scan_interval": 10})
        self.assertEqual(result["data"], {"scan_interval": 10, "future_option": True})

    async def test_malformed_poll_interval_falls_back_without_breaking_setup(self):
        for value in (0, -1, None, "nan", "invalid", True, [], {}):
            with self.subTest(value=value):
                self.assertEqual(scan_interval({"scan_interval": value}), 5)
        self.assertEqual(scan_interval({"scan_interval": 15}), 15)
        self.assertEqual(scan_interval({"scan_interval": 30}), 30)

    def make_flow(self):
        flow = SolutronicInverterConfigFlow()
        flow.hass = self.hass
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = Mock()
        return flow

    async def test_config_flow_creates_same_normalized_entry(self):
        flow = self.make_flow()
        with patch(
            "custom_components.solutronic.config_flow.async_get_sensor_data",
            return_value={"PAC": 100},
        ) as fetch:
            result = await flow.async_step_user({"ip_address": " http://192.0.2.1 "})
        self.assertEqual(result["data"], {"ip_address": "192.0.2.1"})
        flow.async_set_unique_id.assert_awaited_once_with("192.0.2.1")
        fetch.assert_awaited_once_with("192.0.2.1", self.hass)

    async def test_config_flow_distinguishes_response_and_connection_failures(self):
        for error, expected in (
            (TimeoutError(), "cannot_connect"),
            (api.SolutronicInvalidResponseError(), "invalid_response"),
        ):
            with (
                self.subTest(error=type(error).__name__),
                patch(
                    "custom_components.solutronic.config_flow.async_get_sensor_data",
                    side_effect=error,
                ),
            ):
                result = await self.make_flow().async_step_user(
                    {"ip_address": "192.0.2.1"}
                )
            self.assertEqual(result["errors"]["base"], expected)

    async def test_config_flow_does_not_hide_unexpected_errors_as_network_failures(
        self,
    ):
        with (
            patch(
                "custom_components.solutronic.config_flow.async_get_sensor_data",
                side_effect=RuntimeError("unexpected"),
            ),
            self.assertLogs("custom_components.solutronic.config_flow", level="ERROR"),
        ):
            result = await self.make_flow().async_step_user({"ip_address": "192.0.2.1"})
        self.assertEqual(result["errors"]["base"], "unknown")


if __name__ == "__main__":
    unittest.main()
