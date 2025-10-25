import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN, CONF_IP_ADDRESS, DEFAULT_SCAN_INTERVAL
from .coordinator import SolutronicDataUpdateCoordinator
from .discovery import discover_solutronic  # <-- NEW

_LOGGER = logging.getLogger(__name__)


def _clean_ip(value: str) -> str:
    """Normalize user input so only a raw IP remains."""
    value = value.replace("http://", "").replace("https://", "")
    value = value.replace("/solutronic/", "").replace("/solutronic", "")
    if ":" in value:
        value = value.split(":")[0]
    return value.strip()


class SolutronicInverterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the configuration flow for Solutronic Inverter."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        # If a scan button was pressed (no IP entered yet)
        if user_input is not None and user_input.get("scan_network") is True:
            # Attempt automatic device discovery
            ips = await discover_solutronic()

            if ips:
                ip = ips[0]
                _LOGGER.info("Solutronic inverter discovered at %s", ip)

                # Validate discovered IP
                coordinator = SolutronicDataUpdateCoordinator(self.hass, ip, DEFAULT_SCAN_INTERVAL)
                try:
                    await coordinator.async_validate_connection()
                except Exception as e:
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(
                        title=f"Solutronic @ {ip}",
                        data={CONF_IP_ADDRESS: ip},
                    )
            else:
                errors["base"] = "no_devices_found"

        # If a manual IP was submitted
        if user_input is not None and "scan_network" not in user_input:
            ip = _clean_ip(user_input[CONF_IP_ADDRESS])
            coordinator = SolutronicDataUpdateCoordinator(self.hass, ip, DEFAULT_SCAN_INTERVAL)

            try:
                await coordinator.async_validate_connection()
            except Exception as e:
                _LOGGER.error("Solutronic connection test failed: %s", e)
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"Solutronic @ {ip}",
                    data={CONF_IP_ADDRESS: ip}
                )

        # Form UI: manual IP + auto-scan button
        schema = vol.Schema({
            vol.Optional(CONF_IP_ADDRESS, default=""): str,
            vol.Optional("scan_network", default=False): bool,
        })

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SolutronicInverterOptionsFlow(config_entry)


class SolutronicInverterOptionsFlow(config_entries.OptionsFlow):
    """Handle integration options (e.g. update interval)."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema({
            vol.Optional(
                "scan_interval",
                default=self.config_entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
            ): vol.In([5, 10, 30])
        })

        return self.async_show_form(step_id="init", data_schema=schema)