import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN, CONF_IP_ADDRESS, DEFAULT_SCAN_INTERVAL
from .coordinator import SolutronicDataUpdateCoordinator
from .solutronic_api import normalize_ip_address

_LOGGER = logging.getLogger(__name__)


def _clean_ip(value: str) -> str:
    """Normalize and validate user input so only a raw IPv4 address remains."""
    return normalize_ip_address(value)


class SolutronicInverterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Simple configuration flow: manual IP entry only."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        # If user submitted form
        if user_input and CONF_IP_ADDRESS in user_input:
            try:
                ip = _clean_ip(user_input[CONF_IP_ADDRESS])
            except ValueError:
                errors[CONF_IP_ADDRESS] = "invalid_host"
            else:
                await self.async_set_unique_id(ip)
                self._abort_if_unique_id_configured()

                coordinator = SolutronicDataUpdateCoordinator(self.hass, ip, DEFAULT_SCAN_INTERVAL)

                try:
                    await coordinator.async_validate_connection()
                except Exception:
                    _LOGGER.debug("Failed to validate Solutronic inverter at %s", ip, exc_info=True)
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(
                        title=f"Solutronic {ip}",
                        data={CONF_IP_ADDRESS: ip},
                    )

        # Show input form
        schema = vol.Schema({
            vol.Required(CONF_IP_ADDRESS): str,
        })

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SolutronicInverterOptionsFlow(config_entry)


class SolutronicInverterOptionsFlow(config_entries.OptionsFlow):
    """Allows changing scan interval in options."""

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
