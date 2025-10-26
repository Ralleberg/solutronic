import aiohttp
from bs4 import BeautifulSoup
import asyncio

DEFAULT_PORT = 8888
PRIMARY_PATH = "/solutronic/"       # Primary endpoint (test server / proxy environment)
FALLBACK_PATH = "/"                 # Direct inverter endpoint

# Memory cache ensuring we don't probe both paths every update
_BASE_URL_CACHE = {}


def _make_url(ip: str, path: str) -> str:
    """Build full URL reliably."""
    ip = ip.strip()

    # Ensure scheme
    if not ip.startswith("http://") and not ip.startswith("https://"):
        ip = "http://" + ip

    # Ensure port
    if ":" not in ip.split("//")[1]:
        ip = f"{ip}:{DEFAULT_PORT}"

    # Ensure single slash path formatting
    ip = ip.rstrip("/")
    path = path if path.startswith("/") else "/" + path
    return ip + path


async def _probe_working_url(ip: str) -> str:
    """Determine which endpoint path responds and cache it."""
    if ip in _BASE_URL_CACHE:
        return _BASE_URL_CACHE[ip]

    async with aiohttp.ClientSession() as session:
        # Try primary path first (/solutronic/)
        primary = _make_url(ip, PRIMARY_PATH)
        try:
            async with session.get(primary, timeout=4) as response:
                if response.status == 200:
                    _BASE_URL_CACHE[ip] = primary.rstrip("/") + "/"
                    return _BASE_URL_CACHE[ip]
        except Exception:
            pass

        # Try fallback root path
        fallback = _make_url(ip, FALLBACK_PATH)
        try:
            async with session.get(fallback, timeout=4) as response:
                if response.status == 200:
                    _BASE_URL_CACHE[ip] = fallback.rstrip("/") + "/"
                    return _BASE_URL_CACHE[ip]
        except Exception:
            pass

    raise ConnectionError(f"Neither {PRIMARY_PATH} nor {FALLBACK_PATH} responded for {ip}")


async def async_get_raw_html(ip_address: str) -> str:
    """Return raw HTML from whichever inverter endpoint is working."""
    base = await _probe_working_url(ip_address)
    async with aiohttp.ClientSession() as session:
        async with session.get(base, timeout=10) as response:
            return await response.text()


async def async_get_sensor_data(ip_address: str):
    """Fetch and parse inverter telemetry from the discovered working endpoint."""
    base = await _probe_working_url(ip_address)

    async with aiohttp.ClientSession() as session:
        async with session.get(base, timeout=10) as response:
            html_data = await response.text()

    soup = BeautifulSoup(html_data, "html.parser")
    table = soup.find("table")

    data = {}

    if table:
        for row in table.find_all("tr"):
            cols = row.find_all("td")
            if len(cols) == 4:
                key = cols[1].text.strip()
                raw_value = cols[3].text.strip().replace("\xa0", "").strip()

                try:
                    value = float(raw_value.replace(",", "."))
                except ValueError:
                    value = raw_value

                data[key] = value

    return data


async def async_get_mac(ip_address: str):
    """Return MAC address for the device using ARP lookup."""
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