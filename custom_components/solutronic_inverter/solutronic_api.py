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
                value = cols[3].text.strip()
                data[key] = value

    return data