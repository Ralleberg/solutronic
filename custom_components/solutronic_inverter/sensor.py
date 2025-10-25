from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


# Dictionary defining all sensors exposed by this integration.
# Format:
# KEY: (Friendly name, Unit, Device Class, State Class, Icon)
SENSORS = {
    "PAC": ("AC Effekt", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:solar-power"),
    "PACL1": ("L1 Effekt", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:solar-panel"),
    "PACL2": ("L2 Effekt", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:solar-panel"),
    "PACL3": ("L3 Effekt", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:solar-panel"),
    "PAC_TOTAL": ("Samlet Effekt", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:transmission-tower"),
    "UDC1": ("DC Spænding 1", "V", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "mdi:flash-triangle"),
    "UDC2": ("DC Spænding 2", "V", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "mdi:flash-triangle"),
    "UDC3": ("DC Spænding 3", "V", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "mdi:flash-triangle"),
    "IDC1": ("DC Strøm 1", "A", SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT, "mdi:current-dc"),
    "IDC2": ("DC Strøm 2", "A", SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT, "mdi:current-dc"),
    "IDC3": ("DC Strøm 3", "A", SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT, "mdi:current-dc"),
    "ET": ("Dagens Produktion", "kWh", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, "mdi:solar-power"),
    "EG": ("Total Produktion", "kWh", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, "mdi:solar-power"),
    "ETA": ("Effektivitet", "%", SensorDeviceClass.POWER_FACTOR, SensorStateClass.MEASUREMENT, "mdi:percent"),
}


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up sensors when config entry is added."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    # Calculate total AC power (will be added to sensor list if available)
    data = coordinator.data
    if all(k in data for k in ("PACL1", "PACL2", "PACL3")):
        data["PAC_TOTAL"] = data["PACL1"] + data["PACL2"] + data["PACL3"]

    # Create a sensor entity for each supported key that is present in fetched data
    entities = [
        SolutronicSensor(coordinator, key, *values)
        for key, values in SENSORS.items()
        if key in coordinator.data or key == "PAC_TOTAL"
    ]

    async_add_entities(entities)


class SolutronicSensor(CoordinatorEntity, SensorEntity):
    """Representation of a sensor using the shared update coordinator."""

    def __init__(self, coordinator, key, name, unit, device_class, state_class, icon):
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_icon = icon
        self._attr_unique_id = f"{coordinator.ip_address}_{key}"

    @property
    def native_value(self):
        """Return the current sensor value."""
        return self.coordinator.data.get(self._key)

    @property
    def device_info(self):
        """Return device information for grouping all sensors under one device."""
        return {
            "identifiers": {(DOMAIN, self.coordinator.ip_address)},
            "name": self.coordinator.model,        # displayed device name
            "manufacturer": self.coordinator.manufacturer,
            "model": self.coordinator.model,
        }