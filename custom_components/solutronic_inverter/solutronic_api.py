import aiohttp
from bs4 import BeautifulSoup

async def async_get_sensor_data(ip_address: str):
    """Hent og parse inverterdata via HTTP."""
    url = f"http://{ip_address}:8888/solutronic/"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
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

                # Rens værdien (fjerner mellemrum, tab, NBSP osv.)
                raw = cols[3].text.strip().replace("\xa0", "").strip()

                # Forsøg at konvertere til tal
                try:
                    # Håndter både komma og punktum som decimalseparator
                    value = float(raw.replace(",", "."))
                except ValueError:
                    value = raw  # behold original tekst hvis ikke numerisk

                data[key] = value

    return data