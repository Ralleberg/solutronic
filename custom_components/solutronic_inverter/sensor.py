from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

SENSORS = {
    "PAC": ("Solutronic Leistung AC", "W", "power", "mdi:solar-power"),
    "PACL1": ("Solutronic Power L1", "W", "power", "mdi:solar-panel"),
    "PACL2": ("Solutronic Power L2", "W", "power", "mdi:solar-panel"),
    "PACL3": ("Solutronic Power L3", "W", "power", "mdi:solar-panel"),
    "UDC1": ("Solutronic UDC 1", "V", "voltage", "mdi:flash-triangle"),
    "UDC2": ("Solutronic UDC 2", "V", "voltage", "mdi:flash-triangle"),
    "UDC3": ("Solutronic UDC 3", "V", "voltage", "mdi:flash-triangle"),
    "IDC1": ("Solutronic DC current 1", "A", "current", "mdi:current-dc"),
    "IDC2": ("Solutronic DC current 2", "A", "current", "mdi:current-dc"),
    "IDC3": ("Solutronic DC current 3", "A", "current", "mdi:current-dc"),
    "ET": ("Solutronic Energy Today", "kWh", "energy", "mdi:solar-power"),
    "EG": ("Solutronic Energy Total", "kWh", "energy", "mdi:solar-power"),
    "ETA": ("Solutronic Efficiency", "%", "power_factor", "mdi:solar-power-variant"),
}

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [SolutronicSensor(coordinator, key, *vals) for key, vals in SENSORS.items()]
    async_add_entities(entities)

class SolutronicSensor(CoordinatorEntity, Entity):
    def __init__(self, coordinator, key, name, unit, device_class, icon):
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_icon = icon
        self._attr_unique_id = f"{coordinator.ip_address}_{key}"

    @property
    def state(self):
        data = self.coordinator.data
        return data.get(self._key)