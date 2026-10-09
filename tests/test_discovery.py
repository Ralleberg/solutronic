"""Exercise manufacturer UDP discovery without accessing the real network."""

import asyncio
import errno
import ipaddress
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.config_entries import (
    SOURCE_INTEGRATION_DISCOVERY,
    SOURCE_USER,
    ConfigEntryState,
)
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.data_entry_flow import AbortFlow, FlowManager, FlowResultType
from homeassistant.helpers import frame
from voluptuous import Invalid

from custom_components import solutronic
from custom_components.solutronic import config_flow, discovery
from custom_components.solutronic.const import DOMAIN
from custom_components.solutronic.solutronic_api import SolutronicInvalidResponseError

# Protocol B12 section 6.4's complete ACK example, including optional class/OEM.
DOCUMENTED_ACK = bytes.fromhex(
    "53 50 50 2D 41 44 50 2D 41 43 4B 04 C4 00 F5 C0 A8 00 01 "
    "82 32 88 00 00 00 01 00 00 00"
)
ADAPTERS = [
    {
        "enabled": True,
        "ipv4": [{"address": "192.168.0.10", "network_prefix": 24}],
    }
]
CANDIDATE = discovery.DiscoveredInverter("192.168.0.1", "1220")


def ack_for(address):
    """Change the advertised IP in the manufacturer's example reply."""
    return (
        DOCUMENTED_ACK[:15]
        + ipaddress.IPv4Address(address).packed
        + DOCUMENTED_ACK[19:]
    )


class SetupFlowManager(FlowManager):
    """Use HA's actual flow transitions without installing an integration entry."""

    async def async_create_flow(self, handler_key, *, context=None, data=None):
        flow = config_flow.SolutronicInverterConfigFlow()
        flow.init_step = context["source"]
        return flow

    async def async_finish_flow(self, flow, result):
        return result


class DiscoveryProtocolTests(unittest.TestCase):
    def setUp(self):
        self.network = ipaddress.IPv4Network("192.168.0.0/24")

    def test_manufacturer_example_and_minimum_reply(self):
        for packet in (DOCUMENTED_ACK, DOCUMENTED_ACK[:25]):
            self.assertEqual(
                discovery._parse_response(packet, "192.168.0.1", self.network),
                CANDIDATE,
            )

    def test_invalid_packets_and_unreachable_advertised_addresses_are_rejected(self):
        for packet, sender in (
            (DOCUMENTED_ACK[:24], "192.168.0.1"),
            (b"SPP-PRM-SND" + DOCUMENTED_ACK[11:], "192.168.0.1"),
            (DOCUMENTED_ACK + b"x" * 128, "192.168.0.1"),
            (DOCUMENTED_ACK, "192.168.0.2"),
            (DOCUMENTED_ACK, "::1"),
            (DOCUMENTED_ACK, "bad address"),
            (ack_for("192.168.1.1"), "192.168.1.1"),
            (ack_for("192.168.0.255"), "192.168.0.255"),
            (ack_for("192.168.0.0"), "192.168.0.0"),
        ):
            with self.subTest(sender=sender, length=len(packet)):
                self.assertIsNone(
                    discovery._parse_response(packet, sender, self.network)
                )

    def test_collection_deduplicates_ignores_own_ip_and_limits_results(self):
        results = {}
        protocol = discovery._DiscoveryProtocol(self.network, {"192.168.0.10"}, results)
        for _ in range(3):
            protocol.datagram_received(DOCUMENTED_ACK, ("192.168.0.1", 33330))
        protocol.datagram_received(ack_for("192.168.0.10"), ("192.168.0.10", 33330))
        self.assertEqual(list(results), ["192.168.0.1"])
        for host in range(2, 100):
            address = f"192.168.0.{host}"
            protocol.datagram_received(ack_for(address), (address, 33330))
        self.assertEqual(len(results), 64)

    def test_only_enabled_broadcast_capable_ipv4_interfaces_are_used(self):
        adapters = ADAPTERS + [
            {"enabled": False, "ipv4": [{"address": "10.0.0.1", "network_prefix": 24}]},
            {
                "enabled": True,
                "ipv4": [
                    {"address": "127.0.0.1", "network_prefix": 8},
                    {"address": "0.0.0.0", "network_prefix": 0},
                    {"address": "224.0.0.1", "network_prefix": 24},
                    {"address": "10.0.0.1", "network_prefix": 32},
                    {"address": "10.0.0.2", "network_prefix": 31},
                    {"address": "invalid", "network_prefix": 24},
                    {},
                ],
            },
        ]
        self.assertEqual(
            discovery._interfaces(adapters), {"192.168.0.10": self.network}
        )


class DiscoveryAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.hass = HomeAssistant(self.directory.name)
        if hasattr(frame, "async_setup"):
            frame.async_setup(self.hass)
        self.hass.config_entries = SimpleNamespace(
            flow=SimpleNamespace(async_init=AsyncMock(), async_configure=AsyncMock()),
            async_entries=Mock(return_value=[]),
        )
        self.hass.config_entries.async_entry_for_domain_unique_id = Mock(
            side_effect=lambda domain, unique_id: next(
                (
                    entry
                    for entry in self.hass.config_entries.async_entries(domain)
                    if entry.unique_id == unique_id
                ),
                None,
            )
        )
        self.flows = []

    async def asyncTearDown(self):
        for flow in self.flows:
            flow.async_remove()
        await self.hass.async_block_till_done()

    def make_flow(self):
        flow = config_flow.SolutronicInverterConfigFlow()
        flow.hass = self.hass
        flow.flow_id = "test_discovery_flow"
        flow.context = {}
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = Mock()
        self.flows.append(flow)
        return flow

    async def test_broadcasts_exact_read_only_request_and_closes_socket(self):
        transport = Mock()

        async def open_socket(factory, **kwargs):
            protocol = factory()
            protocol.datagram_received(DOCUMENTED_ACK, ("192.168.0.1", 33330))
            protocol.datagram_received(ack_for("192.168.0.20"), ("192.168.0.20", 33330))
            return transport, protocol

        with (
            patch.object(discovery, "async_get_adapters", return_value=ADAPTERS),
            patch.object(discovery, "_DISCOVERY_WINDOW", 0),
            patch.object(
                asyncio.get_running_loop(),
                "create_datagram_endpoint",
                side_effect=open_socket,
            ) as create,
        ):
            result = await discovery.async_discover_inverters(self.hass)
        self.assertEqual(
            [item.ip_address for item in result], ["192.168.0.1", "192.168.0.20"]
        )
        self.assertEqual(create.call_args.kwargs["local_addr"], ("192.168.0.10", 33330))
        self.assertTrue(create.call_args.kwargs["allow_broadcast"])
        self.assertEqual(transport.sendto.call_count, 2)
        transport.sendto.assert_called_with(b"SPP-ADP-REQ", ("192.168.0.255", 33330))
        transport.close.assert_called_once_with()

    async def test_busy_port_falls_back_without_changing_broadcast_destination(self):
        transport = Mock()
        with (
            patch.object(discovery, "async_get_adapters", return_value=ADAPTERS),
            patch.object(discovery, "_DISCOVERY_WINDOW", 0),
            patch.object(
                asyncio.get_running_loop(),
                "create_datagram_endpoint",
                side_effect=[OSError(errno.EADDRINUSE, "busy"), (transport, Mock())],
            ) as create,
        ):
            self.assertEqual(await discovery.async_discover_inverters(self.hass), [])
        self.assertEqual(create.call_args.kwargs["local_addr"], ("192.168.0.10", 0))
        transport.sendto.assert_called_with(b"SPP-ADP-REQ", ("192.168.0.255", 33330))
        transport.close.assert_called_once_with()

    async def test_failed_broadcast_does_not_prevent_other_interface_discovery(self):
        bad_transport = Mock()
        bad_transport.sendto.side_effect = OSError("interface unavailable")
        good_transport = Mock()
        adapters = ADAPTERS + [
            {"enabled": True, "ipv4": [{"address": "10.0.0.10", "network_prefix": 24}]}
        ]

        async def open_socket(factory, **kwargs):
            protocol = factory()
            if kwargs["local_addr"][0] == "192.168.0.10":
                return bad_transport, protocol
            protocol.datagram_received(ack_for("10.0.0.1"), ("10.0.0.1", 33330))
            return good_transport, protocol

        with (
            patch.object(discovery, "async_get_adapters", return_value=adapters),
            patch.object(discovery, "_DISCOVERY_WINDOW", 0),
            patch.object(
                asyncio.get_running_loop(),
                "create_datagram_endpoint",
                side_effect=open_socket,
            ),
        ):
            result = await discovery.async_discover_inverters(self.hass)
        self.assertEqual([item.ip_address for item in result], ["10.0.0.1"])
        good_transport.sendto.assert_called_with(b"SPP-ADP-REQ", ("10.0.0.255", 33330))
        bad_transport.close.assert_called_once_with()
        good_transport.close.assert_called_once_with()

    async def test_unavailable_interfaces_return_no_candidates(self):
        for adapters in ([], ADAPTERS):
            with (
                self.subTest(adapters=bool(adapters)),
                patch.object(discovery, "async_get_adapters", return_value=adapters),
                patch.object(
                    asyncio.get_running_loop(),
                    "create_datagram_endpoint",
                    side_effect=OSError(errno.EADDRNOTAVAIL, "unavailable"),
                ) as create,
            ):
                self.assertEqual(
                    await discovery.async_discover_inverters(self.hass), []
                )
            self.assertEqual(create.call_count, int(bool(adapters)))

    async def test_cancellation_closes_socket(self):
        opened = asyncio.Event()
        transport = Mock()

        async def open_socket(factory, **kwargs):
            opened.set()
            return transport, factory()

        with (
            patch.object(discovery, "async_get_adapters", return_value=ADAPTERS),
            patch.object(
                asyncio.get_running_loop(),
                "create_datagram_endpoint",
                side_effect=open_socket,
            ),
        ):
            task = asyncio.create_task(discovery.async_discover_inverters(self.hass))
            await opened.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        transport.close.assert_called_once_with()

    async def finish_search(self, flow, candidates=None, error=None):
        with patch.object(
            config_flow,
            "async_discover_inverters",
            return_value=candidates or [],
            side_effect=error,
        ):
            initial = await flow.async_step_user()
            await self.hass.async_block_till_done()
        if initial["type"] == FlowResultType.SHOW_PROGRESS:
            self.assertEqual((await flow.async_step_search())["step_id"], "choose")
        else:
            self.assertEqual(initial["type"], FlowResultType.SHOW_PROGRESS_DONE)
        return await flow.async_step_choose()

    async def test_discovered_choice_validates_http_and_keeps_existing_identity(self):
        flow = self.make_flow()
        result = await self.finish_search(flow, [CANDIDATE])
        self.assertEqual(result["step_id"], "choose")
        self.assertEqual(
            result["data_schema"]({"ip_address": CANDIDATE.ip_address}),
            {"ip_address": CANDIDATE.ip_address},
        )
        with self.assertRaises(Invalid):
            result["data_schema"]({"ip_address": "192.168.1.99"})
        with patch.object(
            config_flow, "async_get_sensor_data", return_value={"PAC": 100}
        ) as fetch:
            result = await flow.async_step_choose({"ip_address": CANDIDATE.ip_address})
        self.assertEqual(result["type"], FlowResultType.CREATE_ENTRY)
        self.assertEqual(result["data"], {"ip_address": "192.168.0.1"})
        flow.async_set_unique_id.assert_awaited_once_with("192.168.0.1")
        fetch.assert_awaited_once_with("192.168.0.1", self.hass)

    async def test_no_discovery_or_failed_search_always_allows_manual_entry(self):
        for error in (None, OSError("adapter failure")):
            with self.subTest(error=error):
                flow = self.make_flow()
                result = await self.finish_search(flow, error=error)
                self.assertEqual(result["step_id"], "manual")
                with patch.object(
                    config_flow, "async_get_sensor_data", return_value={"PAC": 100}
                ):
                    result = await flow.async_step_manual({"ip_address": "192.168.0.2"})
                self.assertEqual(result["data"], {"ip_address": "192.168.0.2"})

    async def test_manual_choice_is_available_even_with_discovery_results(self):
        flow = self.make_flow()
        result = await self.finish_search(flow, [CANDIDATE])
        self.assertEqual(
            result["data_schema"]({"ip_address": "manual"}), {"ip_address": "manual"}
        )
        self.assertEqual(
            (await flow.async_step_choose({"ip_address": "manual"}))["step_id"],
            "manual",
        )

    async def test_incompatible_discovered_device_returns_manual_form_with_error(self):
        flow = self.make_flow()
        await self.finish_search(flow, [CANDIDATE])
        with patch.object(
            config_flow,
            "async_get_sensor_data",
            side_effect=SolutronicInvalidResponseError(),
        ):
            result = await flow.async_step_choose({"ip_address": CANDIDATE.ip_address})
        self.assertEqual(result["step_id"], "manual")
        self.assertEqual(result["errors"], {"base": "invalid_response"})

    async def test_closing_progress_flow_cancels_discovery(self):
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def wait_for_discovery(hass):
            started.set()
            try:
                await asyncio.Future()
            finally:
                cancelled.set()

        flow = self.make_flow()
        with patch.object(
            config_flow, "async_discover_inverters", side_effect=wait_for_discovery
        ):
            result = await flow.async_step_user()
            self.assertEqual(result["type"], FlowResultType.SHOW_PROGRESS)
            await started.wait()
            flow.async_remove()
            await cancelled.wait()
            await self.hass.async_block_till_done()
        self.hass.config_entries.flow.async_configure.assert_not_awaited()

    async def test_startup_discovered_card_requires_confirmation_before_http(self):
        flow = self.make_flow()
        with patch.object(
            config_flow, "async_get_sensor_data", return_value={"PAC": 100}
        ) as fetch:
            result = await flow.async_step_integration_discovery(
                {"ip_address": CANDIDATE.ip_address}
            )
            self.assertEqual(result["step_id"], "confirm")
            fetch.assert_not_awaited()
            result = await flow.async_step_confirm({})
        self.assertEqual(result["data"], {"ip_address": CANDIDATE.ip_address})
        fetch.assert_awaited_once_with(CANDIDATE.ip_address, self.hass)

    async def test_existing_installation_is_not_offered_again(self):
        flow = self.make_flow()
        flow._abort_if_unique_id_configured.side_effect = AbortFlow(
            "already_configured"
        )
        with self.assertRaises(AbortFlow) as raised:
            await flow.async_step_integration_discovery(
                {"ip_address": CANDIDATE.ip_address}
            )
        self.assertEqual(raised.exception.reason, "already_configured")
        flow.async_set_unique_id.assert_awaited_once_with(CANDIDATE.ip_address)

    async def test_ha_flow_manager_advances_from_progress_to_selection_and_entry(self):
        manager = SetupFlowManager(self.hass)
        self.hass.config_entries.flow = manager
        self.hass.config_entries.async_entries = Mock(return_value=[])
        release = asyncio.Event()

        async def find_device(hass):
            await release.wait()
            return [CANDIDATE]

        with patch.object(
            config_flow, "async_discover_inverters", side_effect=find_device
        ):
            initial = await manager.async_init(DOMAIN, context={"source": SOURCE_USER})
            self.assertEqual(initial["type"], FlowResultType.SHOW_PROGRESS)
            release.set()
            await self.hass.async_block_till_done()
        choice = await manager.async_configure(initial["flow_id"])
        self.assertEqual(choice["step_id"], "choose")
        with patch.object(
            config_flow, "async_get_sensor_data", return_value={"PAC": 100}
        ):
            result = await manager.async_configure(
                initial["flow_id"], {"ip_address": CANDIDATE.ip_address}
            )
        self.assertEqual(result["type"], FlowResultType.CREATE_ENTRY)
        self.assertEqual(result["data"], {"ip_address": CANDIDATE.ip_address})
        self.assertEqual(result["context"]["unique_id"], CANDIDATE.ip_address)
        self.assertEqual(manager.async_progress(), [])

    async def test_real_ha_unique_id_check_skips_existing_and_in_progress_devices(self):
        manager = SetupFlowManager(self.hass)
        self.hass.config_entries.flow = manager
        self.hass.config_entries.async_entries = Mock(
            return_value=[
                SimpleNamespace(
                    unique_id=CANDIDATE.ip_address,
                    state=ConfigEntryState.LOADED,
                    source=SOURCE_USER,
                )
            ]
        )
        context = {"source": SOURCE_INTEGRATION_DISCOVERY}
        data = {"ip_address": CANDIDATE.ip_address}
        existing = await manager.async_init(DOMAIN, context=dict(context), data=data)
        self.assertEqual(existing["reason"], "already_configured")
        self.hass.config_entries.async_entries.return_value = []
        new = await manager.async_init(DOMAIN, context=dict(context), data=data)
        self.assertEqual(new["step_id"], "confirm")
        repeated = await manager.async_init(DOMAIN, context=dict(context), data=data)
        self.assertEqual(repeated["reason"], "already_in_progress")
        manager.async_abort(new["flow_id"])

    async def test_startup_search_runs_once_after_ha_started(self):
        with patch.object(
            solutronic, "async_discover_inverters", return_value=[CANDIDATE]
        ) as discover:
            self.assertTrue(await solutronic.async_setup(self.hass, {}))
            self.assertTrue(await solutronic.async_setup(self.hass, {}))
            discover.assert_not_awaited()
            self.hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
            await self.hass.async_block_till_done()
            self.hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
            await self.hass.async_block_till_done()
        discover.assert_awaited_once_with(self.hass)
        self.hass.config_entries.flow.async_init.assert_awaited_once_with(
            DOMAIN,
            context={"source": SOURCE_INTEGRATION_DISCOVERY},
            data={"ip_address": CANDIDATE.ip_address},
        )

    async def test_loading_after_startup_searches_immediately(self):
        self.hass.state = CoreState.running
        with patch.object(
            solutronic, "async_discover_inverters", return_value=[]
        ) as discover:
            await solutronic.async_setup(self.hass, {})
            await self.hass.async_block_till_done()
        discover.assert_awaited_once_with(self.hass)

    async def test_startup_failure_does_not_fail_integration_setup(self):
        self.hass.state = CoreState.running
        with patch.object(
            solutronic, "async_discover_inverters", side_effect=OSError("unavailable")
        ):
            self.assertTrue(await solutronic.async_setup(self.hass, {}))
            await self.hass.async_block_till_done()
        self.hass.config_entries.flow.async_init.assert_not_awaited()

    async def test_ha_stop_cancels_pending_startup_search(self):
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def wait_for_discovery(hass):
            started.set()
            try:
                await asyncio.Future()
            finally:
                cancelled.set()

        self.hass.state = CoreState.running
        with patch.object(
            solutronic, "async_discover_inverters", side_effect=wait_for_discovery
        ):
            await solutronic.async_setup(self.hass, {})
            await started.wait()
            self.hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
            await cancelled.wait()
            await self.hass.async_block_till_done()
        self.hass.config_entries.flow.async_init.assert_not_awaited()
