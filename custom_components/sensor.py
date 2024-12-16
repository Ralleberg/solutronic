import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity
from homeassistant.const import ENERGY_KILO_WATT_HOUR, POWER_WATT
import async_timeout
import requests
from bs4 import BeautifulSoup

_LOGGER = logging.getLogger(__name__)
DOMAIN = "solutronic"

SENSOR_TYPES = {
    "ET": {"name": "Total Energy", "unit": ENERGY_KILO_WATT_HOUR},
    "PACL1": {"name": "Power Phase L1", "unit": POWER_WATT},
    "PACL2": {"name": "Power Phase L2", "unit": POWER_WATT},
    "PACL3": {"name": "Power Phase L3", "unit": POWER_WATT},
    "PAC": {"name": "Total Power", "unit": POWER_WATT},
    "UDC1": {"name": "DC Voltage 1", "unit": "V"},
    "UDC2": {"name": "DC Voltage 2", "unit": "V"},
    "IDC1": {"name": "DC Current 1", "unit": "A"},
    "IDC2": {"name": "DC Current 2", "unit": "A"},
    "EG": {"name": "Generated Energy", "unit": ENERGY_KILO_WATT_HOUR},
    "ETA": {"name": "Efficiency", "unit": "%"},
}


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Solutronic sensors"""
    host = config.get("host", "192.168.68.199")
    update_interval = config.get("scan_interval", 30)

    coordinator = SolutronicDataUpdateCoordinator(hass, host, update_interval)
    await coordinator.async_config_entry_first_refresh()

    entities = [SolutronicSensor(coordinator, key) for key in SENSOR_TYPES]
    entities.append(SolutronicTotalPowerSensor(coordinator))  # Add template sensor
    async_add_entities(entities)


class SolutronicDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Solutronic data"""

    def __init__(self, hass, host, update_interval):
        """Initialize the coordinator."""
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=update_interval)
        self.host = host

    async def _async_update_data(self):
        """Fetch data from the Solutronic device."""
        try:
            async with async_timeout.timeout(10):
                response = await self.hass.async_add_executor_job(requests.get, f"http://{self.host}")
                response.raise_for_status()
                html_data = response.text

                # Parse HTML
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
                            data[key] = float(value) if value.replace('.', '', 1).isdigit() else value
                return data
        except Exception as e:
            _LOGGER.error(f"Error fetching Solutronic data: {e}")
            return {}


class SolutronicSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Solutronic sensor"""

    def __init__(self, coordinator, key):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._key = key
        self._attr_name = SENSOR_TYPES[key]["name"]
        self