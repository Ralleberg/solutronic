"""Gateway regression tests replay user-provided frames without inverter access."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import frame
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.solutronic import async_setup_entry, async_unload_entry, spp
from custom_components.solutronic.config_flow import (
    SolutronicInverterConfigFlow,
    SolutronicInverterOptionsFlow,
)
from custom_components.solutronic.const import DOMAIN
from custom_components.solutronic.diagnostics import async_get_config_entry_diagnostics
from custom_components.solutronic.gateway import GatewayCoordinator
from custom_components.solutronic.gateway_sensor import GatewaySensor
from custom_components.solutronic.sensor import async_setup_entry as setup_sensors

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "issue_6_spp_responses.json").read_text()
)
FRAMES = {row["address"]: bytes.fromhex(row["frame"]) for row in FIXTURES}
VALUES = {address: spp.decode_readings(raw, address) for address, raw in FRAMES.items()}
DEVICES = [
    {
        "address": address,
        "serial": str(30537 if address == 30535 else address),
        "model": "SOLPLUS",
        "firmware": "2.65",
    }
    for address in FRAMES
]


def response(source, command, payload=b"\x00\x00\x00\x00"):
    body = (
        b"\x00\x00" + source.to_bytes(2, "big") + command.to_bytes(2, "big") + payload
    )
    return b"\x02" + body + bytes([spp.xor_checksum(body)]) + b"\x03"


class SppParsingTests(unittest.TestCase):
    def test_all_six_real_responses_match_supplied_readings(self):
        names = {
            "PAC_TOTAL": "power_ac_w",
            "UDC1": "udc_v",
            "UACL1": "uac_v",
            "ET": "energy_today_kwh",
            "EG": "energy_total_kwh",
            "FREQUENCY": "grid_hz",
            "TEMPERATURE": "temp_c",
        }
        for row in FIXTURES:
            with self.subTest(address=row["address"]):
                decoded = spp.decode_readings(
                    bytes.fromhex(row["frame"]), row["address"]
                )
                self.assertEqual(
                    decoded, {key: row["expected"][name] for key, name in names.items()}
                )

    def test_requests_match_supplied_master_and_slave_bytes(self):
        samples = [
            (22031, 0x4094, 0, "02 56 0f 00 00 40 94 00 00 00 00 8d 03"),
            (22031, 0x8104, 0, "02 56 0f 00 00 81 04 00 00 00 00 dc 03"),
            (22031, 0x8104, 31, "02 56 0f 00 00 81 04 00 00 00 1f c3 03"),
            (22031, 0x4105, 0, "02 56 0f 00 00 41 05 00 00 00 00 1d 03"),
            (22031, 0x410E, 0, "02 56 0f 00 00 41 0e 00 00 00 00 16 03"),
            (20835, 0x8104, 0, "02 51 63 00 00 81 04 00 00 00 00 b7 03"),
            (20835, 0x8104, 31, "02 51 63 00 00 81 04 00 00 00 1f a8 03"),
            (20835, 0x4105, 0, "02 51 63 00 00 41 05 00 00 00 00 76 03"),
            (20835, 0x410E, 0, "02 51 63 00 00 41 0e 00 00 00 00 7d 03"),
        ]
        for address, command, value, expected in samples:
            self.assertEqual(
                spp.build_request(address, command, value.to_bytes(4, "big")),
                bytes.fromhex(expected),
            )

    def test_bad_checksum_truncated_wrong_device_and_command_rejected(self):
        valid = FRAMES[22031]
        corrupt = bytearray(valid)
        corrupt[50] ^= 1
        for raw, address in [
            (bytes(corrupt), 22031),
            (valid[:-1], 22031),
            (valid, 20835),
            (response(22031, 0x0104), 22031),
        ]:
            with self.subTest(length=len(raw), address=address):
                with self.assertRaises(spp.SppError):
                    spp.decode_readings(raw, address)

    def test_wrong_destination_rejected_even_with_valid_checksum(self):
        raw = bytearray(FRAMES[22031])
        raw[2] = 1
        raw[-2] = spp.xor_checksum(raw[1:-2])
        with self.assertRaises(spp.SppError):
            spp.decode_readings(bytes(raw), 22031)

    def test_zero_energy_and_nighttime_power_are_valid(self):
        raw = bytearray(FRAMES[22031])
        for offset, size in [(24, 4), (40, 4), (48, 2)]:
            raw[7 + offset : 7 + offset + size] = bytes(size)
        raw[-2] = spp.xor_checksum(raw[1:-2])
        values = spp.decode_readings(bytes(raw), 22031)
        self.assertEqual([values[k] for k in ("EG", "ET", "PAC_TOTAL")], [0, 0, 0])

    def test_completely_uninitialized_payload_is_rejected(self):
        with self.assertRaises(spp.SppError):
            spp.decode_readings(response(22031, 0x090E, bytes(128)), 22031)

    def test_metadata_only_frame_cannot_reset_the_energy_baseline(self):
        raw = bytearray(FRAMES[22031])
        for offset, size in [
            (24, 4),
            (40, 4),
            (48, 2),
            (52, 2),
            (54, 2),
            (58, 2),
            (60, 2),
        ]:
            raw[7 + offset : 7 + offset + size] = bytes(size)
        raw[-2] = spp.xor_checksum(raw[1:-2])
        with self.assertRaises(spp.SppError):
            spp.decode_readings(bytes(raw), 22031)

    def test_unknown_request_commands_and_payloads_are_forbidden(self):
        for address, command, payload in [
            (0, 0x410E, bytes(4)),
            (22031, 0xFFFF, bytes(4)),
            (22031, 0x410E, b"\x00\x00\x00\x1f"),
            (22031, 0x8104, b"\x01\x00\x00\x00"),
        ]:
            with self.assertRaises(ValueError):
                spp.build_request(address, command, payload)

    def test_alias_is_explicit_and_payload_identity_is_not_used(self):
        devices = spp.parse_devices("22030,22030\n30535,30537,SOLPLUS 55,2.65")
        self.assertEqual(devices[1].address, 30535)
        self.assertEqual(devices[1].serial, "30537")
        self.assertEqual(spp.decode_readings(FRAMES[22030], 22030), VALUES[22030])

    def test_duplicate_invalid_and_empty_device_lists_rejected(self):
        for value in [
            "",
            "0,1",
            "65536,1",
            "1",
            "1,x",
            "1,2\n1,3",
            "1,2\n3,2",
            "1,2,a,b,c",
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                spp.parse_devices(value)


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.hass = HomeAssistant(self.directory.name)
        if hasattr(frame, "async_setup"):
            frame.async_setup(self.hass)
        self.hass.config_entries = SimpleNamespace(
            async_forward_entry_setups=AsyncMock(),
            async_unload_platforms=AsyncMock(return_value=True),
            async_reload=AsyncMock(),
            async_update_entry=Mock(),
        )
        self.entry = SimpleNamespace(
            entry_id="gateway_entry",
            data={
                "ip_address": "192.0.2.1",
                "connection_type": "tcp_gateway",
                "master_address": 22031,
                "devices": DEVICES,
            },
            options={},
            domain=DOMAIN,
            title="Gateway",
            state=ConfigEntryState.SETUP_IN_PROGRESS,
            pref_disable_polling=False,
            async_on_unload=Mock(),
            add_update_listener=Mock(),
        )
        self.coordinator = GatewayCoordinator(self.hass, self.entry)
        self.addAsyncCleanup(self.coordinator.async_shutdown)
        self.addAsyncCleanup(self.coordinator.async_save_state)

    async def poll(self, values):
        with patch.object(self.coordinator.client, "async_poll", return_value=values):
            self.coordinator.data = await self.coordinator._async_update_data()
        return self.coordinator.data

    def flow(self):
        flow = SolutronicInverterConfigFlow()
        flow.hass = self.hass
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = Mock()
        return flow

    async def test_working_http_setup_remains_identical_and_sends_no_spp(self):
        flow = self.flow()
        form = await flow.async_step_manual()
        self.assertNotIn(
            "use_gateway", form["data_schema"]({"ip_address": "192.0.2.1"})
        )
        with (
            patch(
                "custom_components.solutronic.config_flow.async_get_sensor_data",
                return_value={"PAC": 1},
            ),
            patch.object(spp.SppClient, "async_poll") as tcp,
        ):
            result = await flow.async_step_manual({"ip_address": "192.0.2.1"})
        self.assertEqual(result["data"], {"ip_address": "192.0.2.1"})
        tcp.assert_not_called()
        flow.async_set_unique_id.assert_awaited_once_with("192.0.2.1")

    async def test_http_failure_does_not_offer_or_try_gateway_commands(self):
        flow = self.flow()
        with (
            patch(
                "custom_components.solutronic.config_flow.async_get_sensor_data",
                side_effect=TimeoutError(),
            ),
            patch.object(spp.SppClient, "async_poll") as tcp,
        ):
            form = await flow.async_step_manual({"ip_address": "192.0.2.1"})
        self.assertNotIn(
            "use_gateway", form["data_schema"]({"ip_address": "192.0.2.1"})
        )
        tcp.assert_not_called()

    async def test_explicit_gateway_port_opens_separate_form_without_connecting(self):
        flow = self.flow()
        with patch.object(spp.SppClient, "async_poll") as tcp:
            form = await flow.async_step_manual({"ip_address": "192.0.2.1:33330"})
        self.assertEqual(form["step_id"], "tcp_gateway")
        self.assertEqual(
            form["data_schema"]({"master_address": 22031, "devices": "22031,22031"})[
                "ip_address"
            ],
            "192.0.2.1",
        )
        tcp.assert_not_called()

    async def test_gateway_setup_requires_acceptance_before_connecting(self):
        flow = self.flow()
        with patch.object(spp.SppClient, "async_poll") as tcp:
            result = await flow.async_step_tcp_gateway(
                {
                    "ip_address": "192.0.2.1",
                    "master_address": 22031,
                    "devices": "22031,22031",
                    "accept_experimental": False,
                }
            )
        self.assertEqual(
            result["errors"], {"accept_experimental": "experimental_required"}
        )
        tcp.assert_not_called()

    async def test_gateway_setup_has_separate_identity_and_closes_validation_session(
        self,
    ):
        flow = self.flow()
        with (
            patch.object(spp.SppClient, "async_poll", return_value=VALUES),
            patch.object(spp.SppClient, "async_close") as close,
        ):
            result = await flow.async_step_tcp_gateway(
                {
                    "ip_address": "192.0.2.1",
                    "master_address": 22031,
                    "devices": "22031,22031\n30535,30537",
                    "accept_experimental": True,
                }
            )
        self.assertEqual(result["data"]["connection_type"], "tcp_gateway")
        self.assertEqual(result["data"]["devices"][1]["serial"], "30537")
        flow.async_set_unique_id.assert_awaited_once_with("tcp_gateway:192.0.2.1")
        close.assert_awaited_once()

    async def test_invalid_gateway_config_cannot_send_commands(self):
        with patch.object(spp.SppClient, "async_poll") as tcp:
            for master, devices in [
                (True, "1,2"),
                (70000, "1,2"),
                (22031, "30535,30537"),
            ]:
                result = await self.flow().async_step_tcp_gateway(
                    {
                        "ip_address": "192.0.2.1",
                        "master_address": master,
                        "devices": devices,
                        "accept_experimental": True,
                    }
                )
                self.assertEqual(result["errors"]["base"], "invalid_gateway")
        tcp.assert_not_called()

    async def test_six_separate_devices_and_sensor_ids(self):
        await self.poll(VALUES)
        self.hass.data[DOMAIN] = {self.entry.entry_id: self.coordinator}
        add = Mock()
        await setup_sensors(self.hass, self.entry, add)
        sensors = add.call_args.args[0]
        self.assertEqual(len(sensors), 48)
        self.assertEqual(len({s.unique_id for s in sensors}), 48)
        self.assertEqual(
            len({next(iter(s.device_info["identifiers"])) for s in sensors}), 6
        )
        alias = next(s for s in sensors if s.unique_id == "gateway_entry_spp_30535_EG")
        self.assertEqual(alias.device_info["serial_number"], "30537")
        self.assertEqual(alias.native_value, 60798)

    async def test_partial_failure_only_marks_affected_inverter_unavailable(self):
        await self.poll(VALUES)
        partial = dict(VALUES)
        partial[20835] = None
        await self.poll(partial)
        attributes = ("AC power", "W", None, None, "mdi:solar-power")
        offline = GatewaySensor(
            self.coordinator,
            self.entry.entry_id,
            spp.GatewayDevice(**DEVICES[1]),
            "PAC_TOTAL",
            *attributes,
        )
        online = GatewaySensor(
            self.coordinator,
            self.entry.entry_id,
            spp.GatewayDevice(**DEVICES[0]),
            "PAC_TOTAL",
            *attributes,
        )
        self.assertFalse(offline.available)
        self.assertTrue(online.available)
        self.assertEqual(self.coordinator.data[20835]["EG"], 75497)

    async def test_all_devices_offline_retains_energy_and_reports_failure(self):
        await self.poll(VALUES)
        with self.assertRaises(UpdateFailed):
            await self.poll({address: None for address in VALUES})
        self.assertFalse(self.coordinator.reachable)
        self.assertEqual(self.coordinator._latest[22031]["LIFETIME_DERIVED"], 103058)

    async def test_per_device_energy_is_restored_and_not_double_counted(self):
        await self.poll(VALUES)
        changed = {a: dict(v) for a, v in VALUES.items()}
        changed[22031]["ET"] += 0.1
        await self.poll(changed)
        self.assertEqual(self.coordinator.data[22031]["LIFETIME_DERIVED"], 103058.1)
        self.assertEqual(self.coordinator.data[20835]["LIFETIME_DERIVED"], 75497)
        await self.coordinator.async_save_state()
        restored = GatewayCoordinator(self.hass, self.entry)
        self.addAsyncCleanup(restored.async_shutdown)
        await restored.async_restore_state()
        with patch.object(restored.client, "async_poll", return_value=changed):
            values = await restored._async_update_data()
        self.assertEqual(values[22031]["LIFETIME_DERIVED"], 103058.1)
        self.assertEqual(values[20835]["LIFETIME_DERIVED"], 75497)
        await restored.async_save_state()

    async def test_daily_reset_and_nighttime_keep_existing_counter_behavior(self):
        await self.poll(VALUES)
        values = dict(VALUES[22031])
        values["ET"] = 0
        await self.poll({22031: values})
        values["ET"] = 0.1
        values["PAC_TOTAL"] = 0
        await self.poll({22031: values})
        self.assertEqual(self.coordinator.data[22031]["LIFETIME_DERIVED"], 103058)
        values["ET"] = 0.2
        values["PAC_TOTAL"] = 50
        await self.poll({22031: values})
        self.assertEqual(self.coordinator.data[22031]["LIFETIME_DERIVED"], 103058.1)

    async def test_gateway_diagnostics_redacts_addresses_and_serials(self):
        await self.poll(VALUES)
        self.hass.data[DOMAIN] = {self.entry.entry_id: self.coordinator}
        diagnostic = await async_get_config_entry_diagnostics(self.hass, self.entry)
        encoded = json.dumps(diagnostic)
        for identifier in ("192.0.2.1", "22031", "30535", "30537"):
            self.assertNotIn(identifier, encoded)
        self.assertEqual(len(diagnostic["devices"]), 6)

    async def test_gateway_interval_does_not_change_http_options(self):
        flow = SolutronicInverterOptionsFlow(self.entry)
        form = await flow.async_step_init()
        self.assertEqual(form["data_schema"]({})["scan_interval"], 60)
        result = await flow.async_step_init({"scan_interval": 5})
        self.assertEqual(result["errors"]["scan_interval"], "invalid_gateway_interval")
        result = await flow.async_step_init({"scan_interval": 120})
        self.assertEqual(result["data"]["scan_interval"], 120)

    async def test_gateway_setup_and_unload_close_shared_client(self):
        with patch.object(spp.SppClient, "async_poll", return_value=VALUES):
            self.assertTrue(await async_setup_entry(self.hass, self.entry))
        coordinator = self.hass.data[DOMAIN][self.entry.entry_id]
        with patch.object(coordinator.client, "async_close") as close:
            self.assertTrue(await async_unload_entry(self.hass, self.entry))
            close.assert_awaited_once()


class SppTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        self.connections = 0
        self.stale = False
        self.corrupt_once = False
        self.tasks = set()
        self.server = await asyncio.start_server(self.serve, "127.0.0.1", 0)
        self.client = spp.SppClient(
            "127.0.0.1", 22031, FRAMES, port=self.server.sockets[0].getsockname()[1]
        )

    async def asyncTearDown(self):
        await self.client.async_close()
        self.server.close()
        await self.server.wait_closed()
        for task in tuple(self.tasks):
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)

    async def serve(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        self.connections += 1
        try:
            while True:
                raw = await reader.readexactly(13)
                self.requests.append(raw)
                address = int.from_bytes(raw[1:3], "big")
                command = int.from_bytes(raw[5:7], "big")
                if command == 0x4094:
                    reply = bytes.fromhex("02 00 00 56 0f 00 94 00 00 56 0f 94 03")
                elif command == 0x8104:
                    reply = response(address, 0x0104, raw[7:11])
                elif command == 0x4105:
                    reply = response(address, 0x0105, b"\x00\x00\x00\x14")
                else:
                    reply = FRAMES[address]
                    if self.stale:
                        reply = FRAMES[20835 if address != 20835 else 22031] + reply
                    if self.corrupt_once:
                        self.corrupt_once = False
                        damaged = bytearray(reply)
                        damaged[-2] ^= 1
                        reply = bytes(damaged)
                # Fragment all replies, including frames containing embedded 02/03.
                for start in range(0, len(reply), 5):
                    writer.write(reply[start : start + 5])
                    await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()
            self.tasks.discard(task)

    async def test_real_frames_share_one_connection_with_required_sequence(self):
        first = await self.client.async_poll()
        self.assertEqual(first, VALUES)
        self.assertEqual(self.connections, 1)
        commands = [int.from_bytes(raw[5:7], "big") for raw in self.requests]
        self.assertEqual(commands, [0x4094] + [0x8104, 0x8104, 0x4105, 0x410E] * 6)
        second = await self.client.async_poll()
        self.assertEqual(second, VALUES)
        self.assertEqual(self.connections, 1)
        self.assertEqual(sum(raw[5:7] == b"\x40\x94" for raw in self.requests), 1)

    async def test_coalesced_stale_other_device_response_is_not_misattributed(self):
        self.stale = True
        self.assertEqual(await self.client.async_poll(), VALUES)

    async def test_bad_checksum_reconnects_before_retry(self):
        self.corrupt_once = True
        self.assertEqual(await self.client.async_poll(), VALUES)
        self.assertEqual(self.connections, 2)

    async def test_cancellation_closes_socket(self):
        task = asyncio.create_task(self.client.async_poll())
        await asyncio.sleep(0.02)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertIsNone(self.client._writer)

    async def test_request_retries_are_bounded_and_failed_device_isolated(self):
        self.client.addresses = (22031, 20835)
        original = self.client._poll_device

        async def poll(address):
            if address == 22031:
                with (
                    patch.object(self.client, "_connect", new=AsyncMock()),
                    patch.object(
                        self.client, "_request", side_effect=TimeoutError()
                    ) as request,
                ):
                    result = await original(address)
                    self.assertEqual(request.await_count, 3)
                    return result
            return await original(address)

        with patch.object(self.client, "_poll_device", side_effect=poll):
            values = await self.client.async_poll()
        self.assertIsNone(values[22031])
        self.assertEqual(values[20835], VALUES[20835])

    async def test_shutdown_during_poll_cannot_reconnect(self):
        task = asyncio.create_task(self.client.async_poll())
        await asyncio.sleep(0.02)
        await self.client.async_shutdown()
        result = await task
        self.assertFalse(any(value is not None for value in result.values()))
        self.assertEqual(self.connections, 1)
        self.assertIsNone(self.client._writer)

    async def test_connection_pacing_matches_supplied_delays(self):
        self.client.addresses = (22031,)
        with (
            patch.object(self.client, "_connect", new=AsyncMock()),
            patch.object(self.client, "_request", return_value=FRAMES[22031]),
            patch(
                "custom_components.solutronic.spp.asyncio.sleep", new=AsyncMock()
            ) as pause,
        ):
            result = await self.client.async_poll()
        self.assertEqual(result[22031], VALUES[22031])
        self.assertEqual(
            [call.args[0] for call in pause.await_args_list], [0.05, 0.30, 0.04]
        )
