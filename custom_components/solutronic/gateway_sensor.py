"""Sensors for the explicitly selected experimental gateway mode."""

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from .const import DOMAIN
from .sensor import SENSORS, SolutronicSensor

GATEWAY_SENSORS = {
    key: SENSORS[key]
    for key in ("PAC_TOTAL", "UDC1", "UACL1", "ET", "EG", "LIFETIME_DERIVED")
}
GATEWAY_SENSORS.update(
    {
        "FREQUENCY": (
            "Grid frequency",
            "Hz",
            SensorDeviceClass.FREQUENCY,
            SensorStateClass.MEASUREMENT,
            "mdi:sine-wave",
        ),
        "TEMPERATURE": (
            "Inverter temperature",
            "°C",
            SensorDeviceClass.TEMPERATURE,
            SensorStateClass.MEASUREMENT,
            "mdi:thermometer",
        ),
    }
)


async def async_setup_gateway_sensors(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            GatewaySensor(coordinator, entry.entry_id, device, key, *attributes)
            for device in coordinator.devices
            for key, attributes in GATEWAY_SENSORS.items()
        ]
    )


class GatewaySensor(SolutronicSensor):
    def __init__(self, coordinator, entry_id, device, key, *attributes):
        super().__init__(
            coordinator, f"{entry_id}_spp_{device.address}", key, *attributes
        )
        self._device = device

    @property
    def native_value(self):
        return (
            (self.coordinator.data or {}).get(self._device.address, {}).get(self._key)
        )

    @property
    def available(self):
        return (
            self.coordinator.last_update_success
            and self._device.address in self.coordinator.reachable
            and self.native_value is not None
        )

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": f"Solutronic {self._device.serial}",
            "manufacturer": "Solutronic",
            "model": self._device.model,
            "sw_version": self._device.firmware,
            "serial_number": self._device.serial,
            "configuration_url": f"http://{self.coordinator.ip_address}/",
        }
