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
    #"PAC": ("AC Effekt", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:solar-power"),
    "PAC_TOTAL": ("Samlet AC Effekt", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:solar-power"),

    "PACL1": ("L1 Effekt", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:solar-panel"),
    "PACL2": ("L2 Effekt", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:solar-panel"),
    "PACL3": ("L3 Effekt", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:solar-panel"),

    "UDC1": ("DC Spænding 1", "V", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "mdi:flash-triangle"),
    "UDC2": ("DC Spænding 2", "V", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "mdi:flash-triangle"),
    "UDC3": ("DC Spænding 3", "V", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "mdi:flash-triangle"),

    "IDC1": ("DC Strøm 1", "A", SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT, "mdi:current-dc"),
    "IDC2": ("DC Strøm 2", "A", SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT, "mdi:current-dc"),
    "IDC3": ("DC Strøm 3", "A", SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT, "mdi:current-dc"),

    # --- ENERGY (for Energy Dashboard) ---
    
    "ET": ("Dagens Produktion", "kWh", SensorDeviceClass.ENERGY, SensorStateClass.MEASUREMENT, "mdi:solar-power"),
    "EG": ("Inverter Total", "kWh", SensorDeviceClass.ENERGY, SensorStateClass.MEASUREMENT, "mdi:counter"),

    # Derived lifetime energy (smooth, continuous, no reset spike)
    "LIFETIME_DERIVED": ("Total produktion", "kWh", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, "mdi:solar-power"),

    "MAXP": ("Maks. Effekt i dag", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:trending-up"),
    "ETA": ("Effektivitet", "%", None, SensorStateClass.MEASUREMENT, "mdi:percent"),
    "UACL1": ("Netspænding L1", "V", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "mdi:flash"),
    "UACL2": ("Netspænding L2", "V", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "mdi:flash"),
    "UACL3": ("Netspænding L3", "V", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "mdi:flash"),
}


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up sensors when config entry is added."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        SolutronicSensor(coordinator, entry.entry_id, key, *values)
        for key, values in SENSORS.items()
    ]

    async_add_entities(entities)


class SolutronicSensor(CoordinatorEntity, SensorEntity):
    """Representation of a sensor using the shared update coordinator."""

    def __init__(self, coordinator, entry_id, key, name, unit, device_class, state_class, icon):
        super().__init__(coordinator)
        self._key = key
        self._entry_id = entry_id
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_icon = icon
        self._attr_unique_id = f"{entry_id}_{key}"

        # Mark inverter internal total (EG) as diagnostic
        if key == "EG":
            self._attr_entity_category = "diagnostic"

    @property
    def native_value(self):
        """Return the current sensor value."""
        return self.coordinator.data.get(self._key)

    @property
    def available(self):
        """Return True if the coordinator has successfully updated at least once."""
        return self.coordinator.last_update_success

    @property
    def device_info(self):
        """Return device information for the inverter."""
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": f"Solutronic",
            "manufacturer": self.coordinator.device_manufacturer,
            "model": self.coordinator.device_model,
            "sw_version": self.coordinator.device_firmware,
            "hw_version": getattr(self.coordinator, "device_serial", None),
            "configuration_url": f"http://{self.coordinator.ip_address}/",
        }