"""Experimental SPP gateway transport based on issue #6's supplied frames.

No network requests are made unless this client is explicitly configured. The
meaning of the fixed initialization commands is not documented by the manufacturer.
"""

import asyncio
from dataclasses import dataclass

PORT = 33330
TCP_INTERVALS = (60, 120, 300)


class SppError(ValueError):
    """Invalid or uninitialized gateway response."""


@dataclass(frozen=True)
class GatewayDevice:
    """Bus address and user-confirmed identity; never infer one from the other."""

    address: int
    serial: str
    model: str = "SOLPLUS"
    firmware: str = "Unknown"


def parse_devices(value):
    """Parse address,serial[,model[,firmware]] lines for explicitly selected devices."""
    if not isinstance(value, str):
        raise ValueError("Device list must be text")
    devices = []
    for line in value.splitlines():
        if not line.strip():
            continue
        fields = [part.strip() for part in line.split(",")]
        if not 2 <= len(fields) <= 4 or not fields[0].isdecimal():
            raise ValueError("Use address,serial[,model[,firmware]]")
        address = int(fields[0])
        if not 1 <= address <= 65535 or not fields[1].isdecimal():
            raise ValueError("Invalid address or serial")
        devices.append(
            GatewayDevice(
                address, fields[1], *(part or "Unknown" for part in fields[2:])
            )
        )
    if not 1 <= len(devices) <= 16:
        raise ValueError("Configure between 1 and 16 devices")
    if len({d.address for d in devices}) != len(devices) or len(
        {d.serial for d in devices}
    ) != len(devices):
        raise ValueError("Duplicate address or serial")
    return devices


def xor_checksum(body):
    result = 0
    for value in body:
        result ^= value
    return result


def build_request(address, command, data=b"\x00\x00\x00\x00"):
    """Only construct the fixed sequence observed in the supplied implementation."""
    if (
        not 1 <= address <= 65535
        or command not in (0x4094, 0x8104, 0x4105, 0x410E)
        or data not in (b"\x00\x00\x00\x00", b"\x00\x00\x00\x1f")
        or (data[-1] == 0x1F and command != 0x8104)
    ):
        raise ValueError("Unsupported SPP request")
    body = address.to_bytes(2, "big") + b"\x00\x00" + command.to_bytes(2, "big") + data
    return b"\x02" + body + bytes([xor_checksum(body)]) + b"\x03"


def validate_frame(frame):
    if (
        len(frame) not in (13, 137)
        or frame[0] != 2
        or frame[-1] != 3
        or xor_checksum(frame[1:-2]) != frame[-2]
        or frame[1:3] != b"\x00\x00"
    ):
        raise SppError("Invalid SPP frame")
    return int.from_bytes(frame[3:5], "big"), int.from_bytes(frame[5:7], "big")


def decode_readings(frame, address):
    source, command = validate_frame(frame)
    if len(frame) != 137 or source != address or command != 0x090E:
        raise SppError("Unexpected SPP device or command")
    data = frame[7:-2]
    if not any(data):
        raise SppError("Uninitialized SPP measurements")

    def number(offset, size):
        return int.from_bytes(data[offset : offset + size], "big")

    # Only mappings explicitly supplied and verified by the issue author.
    values = {
        "PAC_TOTAL": number(48, 2),
        "UDC1": number(52, 2),
        "UACL1": number(58, 2),
        "ET": number(24, 4) / 1000,
        "EG": number(40, 4),
        "FREQUENCY": number(54, 2) / 100,
        "TEMPERATURE": number(60, 2),
    }
    if not any(values.values()):
        raise SppError("Uninitialized SPP measurements")
    return values


class SppClient:
    """Serialize a shared master connection with bounded requests and retries."""

    def __init__(self, host, master, addresses, *, port=PORT):
        self.host = host
        self.master = master
        self.addresses = tuple(addresses)
        self.port = port
        self._reader = None
        self._writer = None
        self._lock = asyncio.Lock()
        self._stopped = False

    async def async_shutdown(self):
        """Stop retries as well as closing the current connection on unload."""
        self._stopped = True
        await self.async_close()

    async def async_close(self):
        writer, self._writer = self._writer, None
        self._reader = None
        if writer is not None:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), timeout=2)
            except (OSError, asyncio.TimeoutError):
                pass

    async def _read_frame(self, reader):
        # Fixed lengths, not an ETX delimiter: payloads contain 02/03 themselves.
        header = await reader.readexactly(7)
        if header[0] != 2:
            raise SppError("Invalid SPP frame start")
        command = int.from_bytes(header[5:7], "big")
        if command not in (0x0094, 0x0104, 0x0105, 0x090E):
            raise SppError("Unknown SPP response")
        length = 137 if command == 0x090E else 13
        frame = header + await reader.readexactly(length - 7)
        validate_frame(frame)
        return frame

    async def _request(self, address, command, data=b"\x00\x00\x00\x00"):
        expected = {0x4094: 0x0094, 0x8104: 0x0104, 0x4105: 0x0105, 0x410E: 0x090E}

        reader, writer = self._reader, self._writer
        if reader is None or writer is None or self._stopped:
            raise SppError("SPP connection is closed")

        async def exchange():
            writer.write(build_request(address, command, data))
            await writer.drain()
            # Ignore a bounded number of complete stale frames from other devices.
            for _ in range(8):
                frame = await self._read_frame(reader)
                source, response_command = validate_frame(frame)
                if source != address or response_command != expected[command]:
                    continue
                if command == 0x8104 and frame[7:11] != data:
                    continue
                if command == 0x4094 and frame[9:11] != address.to_bytes(2, "big"):
                    raise SppError("Master handshake identity mismatch")
                return frame
            raise SppError("Too many unexpected SPP replies")

        return await asyncio.wait_for(exchange(), timeout=2)

    async def _connect(self):
        if self._stopped:
            raise SppError("SPP client has been stopped")
        if self._writer is None:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=5
            )
            await self._request(self.master, 0x4094)

    async def _poll_device(self, address):
        for _ in range(3):
            if self._stopped:
                return None
            try:
                await self._connect()
                await self._request(address, 0x8104)
                await asyncio.sleep(0.05)
                await self._request(address, 0x8104, b"\x00\x00\x00\x1f")
                await asyncio.sleep(0.30)
                await self._request(address, 0x4105)
                await asyncio.sleep(0.04)
                frame = await self._request(address, 0x410E)
                return decode_readings(frame, address)
            except (
                OSError,
                asyncio.TimeoutError,
                asyncio.IncompleteReadError,
                SppError,
            ):
                # Reset the connection after an ambiguous/partial reply. Never let
                # leftovers from a timed-out transaction become another reading.
                await self.async_close()
        return None

    async def async_poll(self):
        result = {}
        async with self._lock:
            try:
                async with asyncio.timeout(55):
                    for address in self.addresses:
                        result[address] = await self._poll_device(address)
            except asyncio.TimeoutError:
                await self.async_close()
            except asyncio.CancelledError:
                await self.async_close()
                raise
        return {address: result.get(address) for address in self.addresses}
