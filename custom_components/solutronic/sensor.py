from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


# Dictionary defining all sensors exposed by this integration.
# Format:
# KEY: (Translation Key, Unit, Device Class, State Class, Icon)
SENSORS = {
    # "PAC": ("ac_power", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:solar-power"),
    "PAC_TOTAL": ("total_ac_power", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:solar-power"),

    "PACL1": ("l1_power", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:solar-panel"),
    "PACL2": ("l2_power", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:solar-panel"),
    "PACL3": ("l3_power", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:solar-panel"),

    "UDC1": ("dc_voltage_1", "V", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "mdi:flash-triangle"),
    "UDC2": ("dc_voltage_2", "V", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "mdi:flash-triangle"),
    "UDC3": ("dc_voltage_3", "V", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "mdi:flash-triangle"),

    "IDC1": ("dc_current_1", "A", SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT, "mdi:current-dc"),
    "IDC2": ("dc_current_2", "A", SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT, "mdi:current-dc"),
    "IDC3": ("dc_current_3", "A", SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT, "mdi:current-dc"),

    # --- ENERGY (for Energy Dashboard) ---
    "ET": ("daily_production", "kWh", SensorDeviceClass.ENERGY, SensorStateClass.MEASUREMENT, "mdi:solar-power"),
    "EG": ("inverter_total", "kWh", SensorDeviceClass.ENERGY, SensorStateClass.MEASUREMENT, "mdi:counter"),

    # Derived lifetime energy (smooth, continuous, no reset spike)
    "LIFETIME_DERIVED": ("total_production", "kWh", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, "mdi:solar-power"),

    "MAXP": ("max_power_today", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:trending-up"),
    "ETA": ("efficiency", "%", None, SensorStateClass.MEASUREMENT, "mdi:percent"),
    "UACL1": ("grid_voltage_l1", "V", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "mdi:flash"),
    "UACL2": ("grid_voltage_l2", "V", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "mdi:flash"),
    "UACL3": ("grid_voltage_l3", "V", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "mdi:flash"),
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

    def __init__(self, coordinator, entry_id, key, translation_key, unit, device_class, state_class, icon):
        super().__init__(coordinator)
        self._key = key
        self._entry_id = entry_id
        self._attr_has_entity_name = True
        self._attr_translation_key = translation_key
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
