import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from .workflow import find_solutronic_devices
from .const import DOMAIN

CONF_HOST = "host"

class SolutronicConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solutronic"""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step"""
        if user_input is not None:
            return self.async_create_entry(title="Solutronic", data=user_input)

        # Scan for Solutronic devices
        found_devices = await self.hass.async_add_executor_job(find_solutronic_devices)
        if found_devices:
            # If devices are found, present them as options
            return self.async_show_form(
                step_id="select_device",
                data_schema=vol.Schema(
                    {vol.Required(CONF_HOST): vol.In(found_devices)}
                ),
            )

        # If no devices are found, allow manual input
        return self.async_show_form(
            step_id="manual_input",
            data_schema=vol.Schema({vol.Required(CONF_HOST): str}),
        )

    async def async_step_select_device(self, user_input=None):
        """Handle the selection of a detected device."""
        if user_input is not None:
            return self.async_create_entry(title="Solutronic", data=user_input)

    async def async_step_manual_input(self, user_input=None):
        """Handle manual IP input."""
        if user_input is not None:
            return self.async_create_entry(title="Solutronic", data=user_input)
