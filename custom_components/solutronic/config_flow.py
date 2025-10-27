import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN, CONF_IP_ADDRESS, DEFAULT_SCAN_INTERVAL
from .coordinator import SolutronicDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


def _clean_ip(value: str) -> str:
    """Normalize user input so only a raw IP remains."""
    value = value.replace("http://", "").replace("https://", "")
    value = value.replace("/solutronic/", "").replace("/solutronic", "")
    if ":" in value:
        value = value.split(":")[0]
    return value.strip()


class SolutronicInverterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Simple configuration flow: manual IP entry only."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        # If user submitted form
        if user_input and CONF_IP_ADDRESS in user_input:
            ip = _clean_ip(user_input[CONF_IP_ADDRESS])
            coordinator = SolutronicDataUpdateCoordinator(self.hass, ip, DEFAULT_SCAN_INTERVAL)

            try:
                await coordinator.async_validate_connection()  # Verify inverter connection
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title="Solutronic",
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