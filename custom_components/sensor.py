from homeassistant.components.sensor import SensorEntity
from homeassistant.const import ENERGY_KILO_WATT_HOUR, POWER_WATT
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

class SolutronicSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Solutronic sensor."""

    def __init__(self, coordinator, sensor_name, unit, device_class=None, state_class=None):
        super().__init__(coordinator)
        self._sensor_name = sensor_name
        self._unit = unit
        self._device_class = device_class
        self._state_class = state_class
        self._attr_unique_id = f"solutronic_{sensor_name}"
        self._attr_name = f"Solutronic {sensor_name}"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.coordinator.data.get(self._sensor_name)

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit

    @property
    def device_class(self):
        """Return the device class."""
        return self._device_class

    @property
    def state_class(self):
        """Return the state class."""
        return self._state_class


class SolutronicTotalPowerSensor(SensorEntity):
    """Representation of the total power sensor for Solutronic."""

    def __init__(self, coordinator, sensors):
        self._coordinator = coordinator
        self._sensors = sensors
        self._attr_unique_id = "solutronic_total_power"
        self._attr_name = "Solutronic Total Power"
        self._attr_native_unit_of_measurement = POWER_WATT
        self._attr_device_class = "power"
        self._attr_state_class = "total_increasing"
        self._attr_icon = "mdi:solar-power"

    @property
    def native_value(self):
        """Calculate and return the total power."""
        try:
            total_power = sum(
                float(self._coordinator.data.get(sensor, 0)) for sensor in self._sensors
            )
            return total_power
        except (TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self):
        """Return the extra attributes for the total power sensor."""
        attributes = {}
        for sensor in self._sensors:
            attributes[sensor] = self._coordinator.data.get(sensor, 0)
        return attributes