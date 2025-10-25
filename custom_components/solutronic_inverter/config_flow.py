import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN, CONF_IP_ADDRESS
from .coordinator import SolutronicDataUpdateCoordinator

# Tilføjet logger
_LOGGER = logging.getLogger(__name__)


class SolutronicInverterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solutronic Inverter."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            ip = user_input[CONF_IP_ADDRESS]
            coordinator = SolutronicDataUpdateCoordinator(self.hass, ip)

            try:
                await coordinator.async_validate_connection()
            except Exception as e:
                # Log den faktiske fejl i HA-loggen
                _LOGGER.error("Solutronic forbindelsestest mislykkedes: %s", e)
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"Solutronic @ {ip}",
                    data={CONF_IP_ADDRESS: ip}
                )

        schema = vol.Schema({vol.Required(CONF_IP_ADDRESS): str})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)