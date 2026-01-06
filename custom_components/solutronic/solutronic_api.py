# All comments are in English (per your preference)

import aiohttp
from bs4 import BeautifulSoup
import asyncio
from homeassistant.helpers.aiohttp_client import async_get_clientsession

# We will probe both typical ports and both paths
PORTS_TO_TRY = (8888, 80)
PATHS_TO_TRY = ("/solutronic/", "/")

_BASE_URL_CACHE = {}

# A simple desktop-like User-Agent; some inverters behave better when this is present
_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/123.0 Safari/537.36"
}


def _build_url(ip: str, port: int, path: str) -> str:
    """Build a normalized URL with scheme, port and a single trailing slash."""
    ip = ip.strip()
    if not ip.startswith("http://") and not ip.startswith("https://"):
        ip = "http://" + ip
    # Strip any path and port the user might have typed; we decide those here
    # (config_flow already cleans, but we make this robust)
    host = ip.split("//", 1)[1].split("/", 1)[0].split(":", 1)[0]
    base = f"http://{host}:{port}"
    path = path if path.startswith("/") else "/" + path
    base = base.rstrip("/") + path
    if not base.endswith("/"):
        base += "/"
    return base


def _cache_key(ip: str) -> str:
    """Return a stable cache key (host) regardless of how the user typed the IP."""
    ip = ip.strip()
    if ip.startswith("http://") or ip.startswith("https://"):
        host = ip.split("//", 1)[1].split("/", 1)[0]
    else:
        host = ip.split("/", 1)[0]
    host = host.split(":", 1)[0]
    return host


async def _probe_working_base(ip: str, hass=None, session=None) -> str:
    """Try all port/path combos and return the first that responds with HTTP 200."""
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
                    async with session.get(url, timeout=timeout) as resp:
                        # Many Solutronic pages return 200 with an HTML table right on root
                        if resp.status == 200:
                            _BASE_URL_CACHE[key] = url
                            return url
                except Exception:
                    continue
    finally:
        if owns_session:
            await session.close()

    raise ConnectionError(f"No responding Solutronic endpoint found on {ip} "
                          f"for ports {PORTS_TO_TRY} and paths {PATHS_TO_TRY}.")


async def async_get_raw_html(ip_address: str, hass=None) -> str:
    """Return raw HTML from whichever endpoint is working."""
    timeout = aiohttp.ClientTimeout(total=10)

    if hass is not None:
        session = async_get_clientsession(hass)
        try:
            base = await _probe_working_base(ip_address, hass=hass, session=session)
            try:
                async with session.get(base, timeout=timeout) as response:
                    return await response.text()
            except Exception:
                # Cached base might be stale; clear and reprobe once
                _BASE_URL_CACHE.pop(_cache_key(ip_address), None)
                base = await _probe_working_base(ip_address, hass=hass, session=session)
                async with session.get(base, timeout=timeout) as response:
                    return await response.text()
        except Exception:
            raise

    async with aiohttp.ClientSession(timeout=timeout, headers=_DEFAULT_HEADERS) as session:
        base = await _probe_working_base(ip_address, session=session)
        try:
            async with session.get(base) as response:
                return await response.text()
        except Exception:
            _BASE_URL_CACHE.pop(_cache_key(ip_address), None)
            base = await _probe_working_base(ip_address, session=session)
            async with session.get(base) as response:
                return await response.text()


async def async_get_sensor_data(ip_address: str, hass=None):
    """Fetch and parse inverter telemetry from the discovered working endpoint."""
    timeout = aiohttp.ClientTimeout(total=10)

    if hass is not None:
        session = async_get_clientsession(hass)
        base = await _probe_working_base(ip_address, hass=hass, session=session)
        try:
            async with session.get(base, timeout=timeout) as response:
                html_data = await response.text()
        except Exception:
            _BASE_URL_CACHE.pop(_cache_key(ip_address), None)
            base = await _probe_working_base(ip_address, hass=hass, session=session)
            async with session.get(base, timeout=timeout) as response:
                html_data = await response.text()
    else:
        async with aiohttp.ClientSession(timeout=timeout, headers=_DEFAULT_HEADERS) as session:
            base = await _probe_working_base(ip_address, session=session)
            try:
                async with session.get(base) as response:
                    html_data = await response.text()
            except Exception:
                _BASE_URL_CACHE.pop(_cache_key(ip_address), None)
                base = await _probe_working_base(ip_address, session=session)
                async with session.get(base) as response:
                    html_data = await response.text()

    soup = BeautifulSoup(html_data, "html.parser")
    table = soup.find("table")

    data = {}

    if table:
        for row in table.find_all("tr"):
            cols = row.find_all("td")
            if len(cols) == 4:
                key = cols[1].get_text(strip=True)
                raw_value = cols[3].get_text(strip=True).replace("\xa0", "").strip()
                # Try numeric conversion; fall back to the original string
                try:
                    value = float(raw_value.replace(",", "."))
                except ValueError:
                    value = raw_value
                data[key] = value

    return data


async def async_get_mac(ip_address: str):
    """Return MAC address for the device using ARP lookup (if available)."""
    proc = await asyncio.create_subprocess_shell(
        f"arp -n {ip_address}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    output = stdout.decode().lower()

    for part in output.split():
        if ":" in part and len(part) == 17:
            return part.strip()

    return None