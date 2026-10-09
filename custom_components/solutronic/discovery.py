"""Read-only SOLPLUS UDP discovery (Solutronic protocol B12, section 6.4)."""

import asyncio
import errno
import ipaddress
import logging
import socket
import struct
from dataclasses import dataclass

from homeassistant.components.network import async_get_adapters

_LOGGER = logging.getLogger(__name__)
_PORT = 33330
_REQUEST = b"SPP-ADP-REQ"
_RESPONSE_PREFIX = b"SPP-ADP-ACK"
_DISCOVERY_WINDOW = 3.0
_MAX_RESULTS = 64


@dataclass(frozen=True)
class DiscoveredInverter:
    """A UDP discovery candidate; its HTTP telemetry still needs validation."""

    ip_address: str
    serial: str


def _parse_response(data, sender, network):
    """Validate an ACK, using the reachable sender rather than an arbitrary IP."""
    # The header is followed by SN(2), FW(2), IP(4), TCP port(2), RS485(4).
    # Later firmware can append device-class/OEM fields. The advertised TCP
    # port is the binary protocol port, not an HTTP endpoint.
    if len(data) < 25 or len(data) > 128 or not data.startswith(_RESPONSE_PREFIX):
        return None
    try:
        serial, _, advertised_ip, _ = struct.unpack_from(
            ">HH4sH", data, len(_RESPONSE_PREFIX)
        )
        address = ipaddress.IPv4Address(sender)
    except (ValueError, struct.error):
        return None
    if (
        address not in network
        or address in (network.network_address, network.broadcast_address)
        or address.is_multicast
        or address.is_unspecified
        or address.is_loopback
        or address.packed != advertised_ip
    ):
        return None
    return DiscoveredInverter(str(address), str(serial))


class _DiscoveryProtocol(asyncio.DatagramProtocol):
    """Collect bounded, deduplicated responses on one local interface."""

    def __init__(self, network, own_addresses, results):
        self.network = network
        self.own_addresses = own_addresses
        self.results = results

    def datagram_received(self, data, addr):
        candidate = _parse_response(data, addr[0], self.network)
        if (
            candidate is not None
            and candidate.ip_address not in self.own_addresses
            and len(self.results) < _MAX_RESULTS
        ):
            self.results[candidate.ip_address] = candidate

    def error_received(self, exc):
        _LOGGER.debug("Solutronic UDP discovery socket error: %s", exc)


def _interfaces(adapters):
    """Use only enabled IPv4 interfaces which have a broadcast address."""
    interfaces = {}
    for adapter in adapters:
        if not adapter.get("enabled"):
            continue
        for ipv4 in adapter.get("ipv4", []):
            try:
                interface = ipaddress.IPv4Interface(
                    f"{ipv4['address']}/{ipv4['network_prefix']}"
                )
            except (KeyError, ValueError):
                continue
            if (
                interface.ip.is_loopback
                or interface.ip.is_unspecified
                or interface.ip.is_multicast
                or not 1 <= interface.network.prefixlen <= 30
            ):
                continue
            interfaces[str(interface.ip)] = interface.network
    return interfaces


async def async_discover_inverters(hass):
    """Broadcast twice on HA's enabled interfaces, then close every socket."""
    interfaces = _interfaces(await async_get_adapters(hass))
    if not interfaces:
        return []

    loop = asyncio.get_running_loop()
    results = {}
    transports = []
    try:
        for source, network in interfaces.items():

            def factory(network=network):
                return _DiscoveryProtocol(network, interfaces, results)

            try:
                try:
                    transport, _ = await loop.create_datagram_endpoint(
                        factory,
                        local_addr=(source, _PORT),
                        family=socket.AF_INET,
                        allow_broadcast=True,
                    )
                except OSError as err:
                    if err.errno != errno.EADDRINUSE:
                        raise
                    # Avoid interfering with another program using this port.
                    transport, _ = await loop.create_datagram_endpoint(
                        factory,
                        local_addr=(source, 0),
                        family=socket.AF_INET,
                        allow_broadcast=True,
                    )
                transports.append((transport, str(network.broadcast_address)))
            except OSError:
                _LOGGER.debug(
                    "Could not open Solutronic discovery socket", exc_info=True
                )

        if transports:
            for _ in range(2):
                for transport, broadcast in transports:
                    try:
                        transport.sendto(_REQUEST, (broadcast, _PORT))
                    except OSError:
                        _LOGGER.debug(
                            "Could not send Solutronic discovery broadcast",
                            exc_info=True,
                        )
                await asyncio.sleep(_DISCOVERY_WINDOW / 2)
    finally:
        for transport, _ in transports:
            transport.close()

    return sorted(
        results.values(), key=lambda item: ipaddress.IPv4Address(item.ip_address)
    )
