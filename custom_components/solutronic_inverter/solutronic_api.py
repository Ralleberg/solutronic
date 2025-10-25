import aiohttp
from bs4 import BeautifulSoup

DEFAULT_PORT = 8888
DEFAULT_PATH = "/solutronic/"

def _normalize_url(ip_address: str) -> str:
    """
    Normalize the address to always form a valid inverter URL.

    Examples handled:
      "192.168.1.50"  → "http://192.168.1.50:8888/solutronic/"
      "192.168.1.50:8888"  → "http://192.168.1.50:8888/solutronic/"
      "http://192.168.1.50/solutronic" → "http://192.168.1.50:8888/solutronic/"
    """
    address = ip_address.strip()

    # Ensure scheme
    if not address.startswith("http://") and not address.startswith("https://"):
        address = "http://" + address

    # Ensure port
    if ":" not in address.split("//")[1]:
        address = f"{address}:{DEFAULT_PORT}"

    # Ensure path
    if DEFAULT_PATH not in address:
        if not address.endswith("/"):
            address += "/"
        address += DEFAULT_PATH.strip("/")

    # Ensure trailing slash
    if not address.endswith("/"):
        address += "/"

    return address


async def async_get_raw_html(ip_address: str) -> str:
    """Return raw HTML from the inverter without parsing (used for metadata extraction)."""
    url = _normalize_url(ip_address)
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=10) as response:
            return await response.text()


async def async_get_sensor_data(ip_address: str):
    """Fetch and parse inverter telemetry values."""
    url = _normalize_url(ip_address)

    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=10) as response:
            html_data = await response.text()

    soup = BeautifulSoup(html_data, "html.parser")
    table = soup.find("table")

    data = {}

    if table:
        rows = table.find_all("tr")
        for row in rows:
            cols = row.find_all("td")
            if len(cols) == 4:
                key = cols[1].text.strip()

                # Clean the value (remove whitespace, NBSP, formatting)
                raw_value = cols[3].text.strip().replace("\xa0", "").strip()

                # Attempt numeric conversion
                try:
                    value = float(raw_value.replace(",", "."))
                except ValueError:
                    value = raw_value  # Keep original if non-numeric

                data[key] = value

    return data