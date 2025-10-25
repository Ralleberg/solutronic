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
    # Extract model + manufacturer from <h1> block if available
    # Example structure:
    #
    #   <h1>
    #     SOLPLUS 100
    #     <br>
    #     Solutronic AG
    #   </h1>
    # ------------------------------------------------------------------
    h1 = soup.find("h1")
    manufacturer = "Solutronic"
    model = "Inverter"

    if h1:
        # Split by line breaks (BS4 preserves text separated by <br>)
        lines = [line.strip() for line in h1.text.strip().split("\n") if line.strip()]
        if len(lines) >= 1:
            model = lines[0]
        if len(lines) >= 2:
            manufacturer = lines[1]

    # Store values under internal keys
    data["_manufacturer"] = manufacturer
    data["_model"] = model

    # ------------------------------------------------------------------
    # Extract tabular measurement data
    # ------------------------------------------------------------------
    table = soup.find("table")
    if table:
        rows = table.find_all("tr")
        for row in rows:
            cols = row.find_all("td")
            if len(cols) == 4:
                key = cols[1].text.strip()

                # Clean the numeric/text value
                raw = cols[3].text.strip().replace("\xa0", "").strip()

                # Convert to number if possible
                try:
                    value = float(raw.replace(",", "."))
                except ValueError:
                    value = raw  # fallback: keep as string

                data[key] = value

    return data
