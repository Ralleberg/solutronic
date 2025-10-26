import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN, CONF_IP_ADDRESS, DEFAULT_SCAN_INTERVAL
from .coordinator import SolutronicDataUpdateCoordinator
from .discovery import discover_solutronic

_LOGGER = logging.getLogger(__name__)


def _clean_ip(value: str) -> str:
    """Normalize user input so only a raw IP remains."""
    value = value.replace("http://", "").replace("https://", "")
    value = value.replace("/solutronic/", "").replace("/solutronic", "")
    if ":" in value:
        value = value.split(":")[0]
    return value.strip()


class SolutronicInverterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the configuration flow."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Start setup: begin auto-discovery via progress screen."""
        return self.async_show_progress(
            step_id="scan",
            progress_action="scan_network"
        )

    async def async_step_scan_network(self, progress_input=None):
        """Actual network scan runs here."""
        ips = await discover_solutronic()

        if ips:
            ip = ips[0]
            coordinator = SolutronicDataUpdateCoordinator(self.hass, ip, DEFAULT_SCAN_INTERVAL)

            try:
                await coordinator.async_validate_connection()
                return self.async_show_progress_done(
                    next_step_id="finish",
                    data={CONF_IP_ADDRESS: ip},
                )
            except Exception:
                pass  # fallback to manual entry

        # Nothing found → move to manual step
        return self.async_show_progress_done(next_step_id="manual")

    async def async_step_manual(self, user_input=None):
        """Manual IP fallback form."""
        errors = {}

        if user_input and CONF_IP_ADDRESS in user_input:
            ip = _clean_ip(user_input[CONF_IP_ADDRESS])
            coordinator = SolutronicDataUpdateCoordinator(self.hass, ip, DEFAULT_SCAN_INTERVAL)

            try:
                await coordinator.async_validate_connection()
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"Solutronic @ {ip}",
                    data={CONF_IP_ADDRESS: ip}
                )

        schema = vol.Schema({
            vol.Required(CONF_IP_ADDRESS): str,
        })

        return self.async_show_form(step_id="manual", data_schema=schema, errors=errors)

    async def async_step_finish(self, user_input):
        """Finish and create config entry from auto-discovery."""
        return self.async_create_entry(
            title=f"Solutronic @ {user_input[CONF_IP_ADDRESS]}",
            data=user_input
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SolutronicInverterOptionsFlow(config_entry)


class SolutronicInverterOptionsFlow(config_entries.OptionsFlow):
    """Handle integration options such as polling interval."""

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