import aiohttp
from bs4 import BeautifulSoup

async def async_get_sensor_data(ip_address: str):
    """Fetch and parse inverter data via HTTP."""
    url = f"http://{ip_address}:8888/solutronic/"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            html_data = await response.text()

    soup = BeautifulSoup(html_data, "html.parser")
    data = {}

    # ------------------------------------------------------------------
    # Extract model + manufacturer from <h1>
    # ------------------------------------------------------------------
    h1 = soup.find("h1")
    manufacturer = "Solutronic"
    model = "Inverter"

    if h1:
        lines = [line.strip() for line in h1.text.strip().split("\n") if line.strip()]
        if len(lines) >= 1:
            model = lines[0]
        if len(lines) >= 2:
            manufacturer = lines[1]

    data["_manufacturer"] = manufacturer
    data["_model"] = model

    # ------------------------------------------------------------------
    # Extract firmware and build info near top of page
    # Example:
    # FW-Release: 1.42
    # Build: Aug 15 2012 16:56:39
    # ------------------------------------------------------------------
    page_text = soup.text
    for line in page_text.splitlines():
        line = line.strip()
        if line.startswith("FW-Release"):
            data["_firmware"] = line.replace("FW-Release:", "").strip()
        elif line.startswith("Build:"):
            data["_build"] = line.replace("Build:", "").strip()

    # Defaults if nothing found
    data.setdefault("_firmware", "Unknown")
    data.setdefault("_build", "Unknown")

    # ------------------------------------------------------------------
    # Extract table sensor values
    # ------------------------------------------------------------------
    table = soup.find("table")
    if table:
        rows = table.find_all("tr")
        for row in rows:
            cols = row.find_all("td")
            if len(cols) == 4:
                key = cols[1].text.strip()
                raw = cols[3].text.strip().replace("\xa0", "").strip()
                try:
                    value = float(raw.replace(",", "."))
                except ValueError:
                    value = raw
                data[key] = value

    return data