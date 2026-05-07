import aiohttp
from bs4 import BeautifulSoup
import asyncio
import ipaddress
import logging
import re
from urllib.parse import urlsplit

from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

PORTS_TO_TRY = (8888, 80)
PATHS_TO_TRY = ("/solutronic/", "/")

_BASE_URL_CACHE = {}

# A simple desktop-like User-Agent; some inverters behave better when this is present
_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/123.0 Safari/537.36"
}

KNOWN_SENSOR_KEYS = {
    "PAC", "PACL1", "PACL2", "PACL3", "UDC1", "UDC2", "UDC3",
    "IDC1", "IDC2", "IDC3", "IAC1", "ET", "EG", "SN", "MAXP", "ETA",
    "UACL1", "UACL2", "UACL3",
}
TELEMETRY_SENSOR_KEYS = KNOWN_SENSOR_KEYS - {"SN"}


class SolutronicConnectionError(ConnectionError):
    """Raised when no Solutronic endpoint can be reached."""


class SolutronicInvalidResponseError(ValueError):
    """Raised when an endpoint responds but does not expose inverter data."""


def normalize_ip_address(value: str) -> str:
    """Return a validated IPv4 address from user input or URL-like input."""
    if not isinstance(value, str):
        raise ValueError("IP address must be a string")

    raw_value = value.strip()
    if not raw_value:
        raise ValueError("IP address is required")

    parsed = urlsplit(raw_value if "://" in raw_value else f"http://{raw_value}")
    host = parsed.hostname
    if host is None:
        raise ValueError("IP address is invalid")

    try:
        ip = ipaddress.ip_address(host)
    except ValueError as err:
        raise ValueError("IP address is invalid") from err

    if ip.version != 4:
        raise ValueError("Only IPv4 addresses are supported")

    return str(ip)


def _build_url(ip: str, port: int, path: str) -> str:
    """Build a normalized URL with scheme, port and a single trailing slash."""
    host = normalize_ip_address(ip)
    base = f"http://{host}:{port}"
    path = path if path.startswith("/") else "/" + path
    base = base.rstrip("/") + path
    if not base.endswith("/"):
        base += "/"
    return base


def _cache_key(ip: str) -> str:
    """Return a stable cache key (host) regardless of how the user typed the IP."""
    return normalize_ip_address(ip)


async def _fetch_text(session, url: str, timeout: aiohttp.ClientTimeout) -> str:
    """Fetch text from a URL and fail on non-successful HTTP statuses."""
    async with session.get(url, timeout=timeout, headers=_DEFAULT_HEADERS) as response:
        response.raise_for_status()
        return await response.text()


def _parse_sensor_data(html_data: str) -> dict:
    """Parse inverter telemetry from supported Solutronic HTML layouts."""
    data = _parse_table_sensor_data(html_data)
    if TELEMETRY_SENSOR_KEYS.intersection(data):
        return data

    legacy_data = _parse_basic_menu_sensor_data(html_data)
    return legacy_data or data


def _parse_table_sensor_data(html_data: str) -> dict:
    """Parse telemetry from newer Solutronic table layouts."""
    soup = BeautifulSoup(html_data, "html.parser")
    table = soup.find("table")
    data = {}

    if not table:
        return data

    for row in table.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) != 4:
            continue

        key = cols[1].get_text(strip=True)
        if not key:
            continue

        raw_value = cols[3].get_text(strip=True).replace("\xa0", "").strip()
        try:
            value = float(raw_value.replace(",", "."))
        except ValueError:
            value = raw_value
        data[key] = value

    return data


def _to_float(value: str):
    """Convert a Solutronic number string to float."""
    return float(value.replace(",", ".").strip())


def _extract_labeled_number(text: str, label: str):
    """Extract the numeric value after a label from the legacy basic menu page."""
    match = re.search(
        rf"{re.escape(label)}\s*:\s*([+-]?\d+(?:[.,]\d+)?)",
        text,
        re.IGNORECASE,
    )
    if match is None:
        return None

    return _to_float(match.group(1))


def _parse_basic_menu_sensor_data(html_data: str) -> dict:
    """Parse telemetry from old SOLPLUS basic menu HTML pages."""
    soup = BeautifulSoup(html_data, "html.parser")
    text = soup.get_text("\n", strip=True)

    if "webserver for solplus" not in text.lower() and "solplus" not in text.lower():
        return {}

    data = {}

    label_map = {
        "power AC": "PAC",
        "mains voltage": "UACL1",
        "mains current": "IAC1",
        "DC voltage": "UDC1",
        "DC-current": "IDC1",
        "energy today": "ET",
        "energy total": "EG",
        "efficiency": "ETA",
        "maximum power today": "MAXP",
    }

    for label, key in label_map.items():
        value = _extract_labeled_number(text, label)
        if value is not None:
            data[key] = value

    if "PAC" in data:
        data.setdefault("PACL1", data["PAC"])

    serial_match = re.search(r"S/N\s+(\d+)", text, re.IGNORECASE)
    if serial_match is not None:
        data["SN"] = serial_match.group(1)

    return data


def _looks_like_solutronic_page(html_data: str) -> bool:
    """Return True only for pages that look like a Solutronic inverter page."""
    data = _parse_sensor_data(html_data)
    if TELEMETRY_SENSOR_KEYS.intersection(data):
        return True

    lower_html = html_data.lower()
    return (
        "solutronic" in lower_html
        or "solplus" in lower_html
        or "fw-release" in lower_html
    )


async def _probe_working_base(ip: str, hass=None, session=None) -> str:
    """Try all port/path combos and return the first Solutronic-looking endpoint."""
    key = _cache_key(ip)
    if key in _BASE_URL_CACHE:
        return _BASE_URL_CACHE[key]

    timeout = aiohttp.ClientTimeout(total=8)

    owns_session = False
    if session is None:
        if hass is not None:
            session = async_get_clientsession(hass)
        else:
            session = aiohttp.ClientSession(timeout=timeout, headers=_DEFAULT_HEADERS)
            owns_session = True

    try:
        for port in PORTS_TO_TRY:
            for path in PATHS_TO_TRY:
                url = _build_url(ip, port, path)
                try:
                    html_data = await _fetch_text(session, url, timeout)
                except (aiohttp.ClientError, asyncio.TimeoutError):
                    _LOGGER.debug("Solutronic probe failed for %s", url, exc_info=True)
                    continue

                if _looks_like_solutronic_page(html_data):
                    _BASE_URL_CACHE[key] = url
                    return url
    finally:
        if owns_session:
            await session.close()

    raise SolutronicConnectionError(
        f"No Solutronic endpoint found on {ip} for ports {PORTS_TO_TRY} "
        f"and paths {PATHS_TO_TRY}."
    )


async def async_get_raw_html(ip_address: str, hass=None) -> str:
    """Return raw HTML from whichever endpoint is working."""
    timeout = aiohttp.ClientTimeout(total=10)

    if hass is not None:
        session = async_get_clientsession(hass)
        try:
            base = await _probe_working_base(ip_address, hass=hass, session=session)
            try:
                return await _fetch_text(session, base, timeout)
            except (aiohttp.ClientError, asyncio.TimeoutError):
                # Cached base might be stale; clear and reprobe once
                _BASE_URL_CACHE.pop(_cache_key(ip_address), None)
                base = await _probe_working_base(ip_address, hass=hass, session=session)
                return await _fetch_text(session, base, timeout)
        except ValueError:
            raise

    async with aiohttp.ClientSession(timeout=timeout, headers=_DEFAULT_HEADERS) as session:
        base = await _probe_working_base(ip_address, session=session)
        try:
            return await _fetch_text(session, base, timeout)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            _BASE_URL_CACHE.pop(_cache_key(ip_address), None)
            base = await _probe_working_base(ip_address, session=session)
            return await _fetch_text(session, base, timeout)


async def async_get_sensor_data(ip_address: str, hass=None):
    """Fetch and parse inverter telemetry from the discovered working endpoint."""
    timeout = aiohttp.ClientTimeout(total=10)

    if hass is not None:
        session = async_get_clientsession(hass)
        base = await _probe_working_base(ip_address, hass=hass, session=session)
        try:
            html_data = await _fetch_text(session, base, timeout)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            _BASE_URL_CACHE.pop(_cache_key(ip_address), None)
            base = await _probe_working_base(ip_address, hass=hass, session=session)
            html_data = await _fetch_text(session, base, timeout)
    else:
        async with aiohttp.ClientSession(timeout=timeout, headers=_DEFAULT_HEADERS) as session:
            base = await _probe_working_base(ip_address, session=session)
            try:
                html_data = await _fetch_text(session, base, timeout)
            except (aiohttp.ClientError, asyncio.TimeoutError):
                _BASE_URL_CACHE.pop(_cache_key(ip_address), None)
                base = await _probe_working_base(ip_address, session=session)
                html_data = await _fetch_text(session, base, timeout)

    data = _parse_sensor_data(html_data)
    if not TELEMETRY_SENSOR_KEYS.intersection(data):
        raise SolutronicInvalidResponseError("Endpoint did not return Solutronic telemetry")

    return data
