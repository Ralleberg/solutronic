from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


# Dictionary defining all sensors exposed by this integration.
# Format:
# KEY: (English Name, Unit, Device Class, State Class, Icon)
SENSORS = {
    # "PAC": ("AC power", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:solar-power"),
    "PAC_TOTAL": ("Total AC power", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:solar-power"),

    "PACL1": ("L1 power", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:solar-panel"),
    "PACL2": ("L2 power", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:solar-panel"),
    "PACL3": ("L3 power", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:solar-panel"),

    "UDC1": ("DC voltage 1", "V", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "mdi:flash-triangle"),
    "UDC2": ("DC voltage 2", "V", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "mdi:flash-triangle"),
    "UDC3": ("DC voltage 3", "V", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "mdi:flash-triangle"),

    "IDC1": ("DC current 1", "A", SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT, "mdi:current-dc"),
    "IDC2": ("DC current 2", "A", SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT, "mdi:current-dc"),
    "IDC3": ("DC current 3", "A", SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT, "mdi:current-dc"),

    # --- ENERGY (for Energy Dashboard) ---
    "ET": ("Daily production", "kWh", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, "mdi:solar-power"),
    "EG": ("Inverter total", "kWh", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, "mdi:counter"),

    # Derived lifetime energy (smooth, continuous, no reset spike)
    "LIFETIME_DERIVED": ("Total production", "kWh", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, "mdi:solar-power"),

    "MAXP": ("Maximum power today", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:trending-up"),
    "ETA": ("Efficiency", "%", None, SensorStateClass.MEASUREMENT, "mdi:percent"),
    "UACL1": ("Grid voltage L1", "V", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "mdi:flash"),
    "UACL2": ("Grid voltage L2", "V", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "mdi:flash"),
    "UACL3": ("Grid voltage L3", "V", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "mdi:flash"),
}


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up sensors when config entry is added."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    supported_keys = set(coordinator.data or {})

    # If the inverter was reachable during setup, only create entities for
    # values this model actually reports. If setup starts while the inverter is
    # temporarily offline, keep the broad entity set so existing installs still
    # recover when data returns.
    if supported_keys:
        sensor_items = [
            (key, values)
            for key, values in SENSORS.items()
            if key in supported_keys
        ]
    else:
        sensor_items = SENSORS.items()

    entities = [
        SolutronicSensor(coordinator, entry.entry_id, key, *values)
        for key, values in sensor_items
    ]

    async_add_entities(entities)


class SolutronicSensor(CoordinatorEntity, SensorEntity):
    """Representation of a sensor using the shared update coordinator."""

    def __init__(self, coordinator, entry_id, key, name, unit, device_class, state_class, icon):
        super().__init__(coordinator)
        self._key = key
        self._entry_id = entry_id
        self._attr_has_entity_name = True
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_icon = icon
        self._attr_unique_id = f"{entry_id}_{key}"

        # Mark inverter internal total (EG) as diagnostic
        if key == "EG":
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        """Return the current sensor value."""
        return (self.coordinator.data or {}).get(self._key)

    @property
    def available(self):
        """Return True if the coordinator has successfully updated at least once."""
        return self.coordinator.last_update_success and self._key in (self.coordinator.data or {})

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
