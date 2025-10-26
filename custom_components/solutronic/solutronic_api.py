# All comments are in English (per your preference)

import aiohttp
from bs4 import BeautifulSoup
import asyncio

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


async def _probe_working_base(ip: str) -> str:
    """Try all port/path combos and return the first that responds with HTTP 200."""
    if ip in _BASE_URL_CACHE:
        return _BASE_URL_CACHE[ip]

    timeout = aiohttp.ClientTimeout(total=8)
    async with aiohttp.ClientSession(timeout=timeout, headers=_DEFAULT_HEADERS) as session:
        for port in PORTS_TO_TRY:
            for path in PATHS_TO_TRY:
                url = _build_url(ip, port, path)
                try:
                    async with session.get(url) as resp:
                        # Many Solutronic pages return 200 with an HTML table right on root
                        if resp.status == 200:
                            _BASE_URL_CACHE[ip] = url
                            return url
                except Exception:
                    # Try next combination
                    continue

    raise ConnectionError(f"No responding Solutronic endpoint found on {ip} "
                          f"for ports {PORTS_TO_TRY} and paths {PATHS_TO_TRY}.")


async def async_get_raw_html(ip_address: str) -> str:
    """Return raw HTML from whichever endpoint is working."""
    base = await _probe_working_base(ip_address)
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout, headers=_DEFAULT_HEADERS) as session:
        async with session.get(base) as response:
            return await response.text()


async def async_get_sensor_data(ip_address: str):
    """Fetch and parse inverter telemetry from the discovered working endpoint."""
    base = await _probe_working_base(ip_address)

    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout, headers=_DEFAULT_HEADERS) as session:
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