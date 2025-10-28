from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.components.integration.sensor import IntegrationSensor
from homeassistant.const import UnitOfEnergy
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


# Dictionary defining all sensors exposed by this integration.
# Format:
# KEY: (Friendly name, Unit, Device Class, State Class, Icon)
SENSORS = {
    # Power sensors
    "PAC_TOTAL": ("Samlet AC Effekt", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:solar-power"),
    "PACL1": ("L1 Effekt", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:solar-panel"),
    "PACL2": ("L2 Effekt", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:solar-panel"),
    "PACL3": ("L3 Effekt", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:solar-panel"),

    # DC voltage & current
    "UDC1": ("DC Spænding 1", "V", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "mdi:flash-triangle"),
    "UDC2": ("DC Spænding 2", "V", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "mdi:flash-triangle"),
    "UDC3": ("DC Spænding 3", "V", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "mdi:flash-triangle"),

    "IDC1": ("DC Strøm 1", "A", SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT, "mdi:current-dc"),
    "IDC2": ("DC Strøm 2", "A", SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT, "mdi:current-dc"),
    "IDC3": ("DC Strøm 3", "A", SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT, "mdi:current-dc"),

    # Energy sensors
    "ET": ("Dagens Produktion", "kWh", SensorDeviceClass.ENERGY, SensorStateClass.MEASUREMENT, "mdi:solar-power"),
    "EG": ("Inverter Total", "kWh", SensorDeviceClass.ENERGY, SensorStateClass.MEASUREMENT, "mdi:solar-power"),
    "LIFETIME_DERIVED": ("Total produktion", "kWh", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, "mdi:solar-power"),

    # Misc sensors
    "MAXP": ("Maks. Effekt i dag", "W", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "mdi:trending-up"),
    "ETA": ("Effektivitet", "%", None, SensorStateClass.MEASUREMENT, "mdi:percent"),
    "UACL1": ("Netspænding L1", "V", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "mdi:flash"),
    "UACL2": ("Netspænding L2", "V", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "mdi:flash"),
    "UACL3": ("Netspænding L3", "V", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, "mdi:flash"),
}


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Solutronic sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        SolutronicSensor(coordinator, key, *values)
        for key, values in SENSORS.items()
        if key in coordinator.data
    ]

    # Tilføj også en integreret energisensor baseret på PAC_TOTAL
    pac_entity = next((e for e in entities if e._key == "PAC_TOTAL"), None)
    if pac_entity:
        integration_sensor = SolutronicIntegrationSensor(
            hass=hass,
            coordinator=coordinator,
            source_entity=pac_entity,
        )
        entities.append(integration_sensor)

    async_add_entities(entities)


class SolutronicSensor(CoordinatorEntity, SensorEntity):
    """Representation of a regular Solutronic sensor."""

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
        """Return current sensor value."""
        return self.coordinator.data.get(self._key)

    @property
    def device_info(self):
        """Return metadata for the inverter."""
        return {
            "identifiers": {(DOMAIN, self.coordinator.ip_address)},
            "name": "Solutronic",
            "manufacturer": self.coordinator.device_manufacturer,
            "model": self.coordinator.device_model,
            "sw_version": self.coordinator.device_firmware,
            "hw_version": getattr(self.coordinator, "device_serial", None),
            "configuration_url": f"http://{self.coordinator.ip_address}/",
        }


class SolutronicIntegrationSensor(IntegrationSensor):
    """Integration-based energy sensor (kWh) derived from PAC_TOTAL."""

    def __init__(self, hass, coordinator, source_entity):
        """Initialize energy integration sensor."""
        super().__init__(
            source_entity=source_entity.entity_id,
            name="Solutronic total produktion (beregnet)",
            unique_id=f"{coordinator.ip_address}_integrated_energy",
            unit_prefix="k",
            unit_time="h",
            integration_method="trapezoidal",
        )

        self.hass = hass
        self.coordinator = coordinator
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_icon = "mdi:solar-power"

    @property
    def device_info(self):
        """Ensure it's grouped under the same device."""
        return {
            "identifiers": {(DOMAIN, self.coordinator.ip_address)},
            "name": "Solutronic",
            "manufacturer": self.coordinator.device_manufacturer,
            "model": self.coordinator.device_model,
            "sw_version": self.coordinator.device_firmware,
            "hw_version": getattr(self.coordinator, "device_serial", None),
            "configuration_url": f"http://{self.coordinator.ip_address}/",
        }