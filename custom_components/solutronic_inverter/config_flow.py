import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN, CONF_IP_ADDRESS, DEFAULT_SCAN_INTERVAL
from .coordinator import SolutronicDataUpdateCoordinator
from .discovery import discover_solutronic  # Auto-discovery

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
        """Initial setup step: try auto-discovery first."""
        # Show progress UI
        self.async_show_progress(
            step_id="user",
            progress_action="scan_network",
            description="config.solutronic.scan_description"
        )

        ips = await discover_solutronic()

        # Close progress UI
        self.async_show_progress_done(step_id="user")

        if ips:
            ip = ips[0]
            _LOGGER.info("Solutronic inverter discovered at %s", ip)

            coordinator = SolutronicDataUpdateCoordinator(self.hass, ip, DEFAULT_SCAN_INTERVAL)
            try:
                await coordinator.async_validate_connection()
            except Exception:
                # If inverter responds badly → fallback to manual form
                return await self.async_step_manual({})
            else:
                return self.async_create_entry(
                    title=f"Solutronic @ {ip}",
                    data={CONF_IP_ADDRESS: ip},
                )

        # No device found → go to manual entry
        return await self.async_step_manual({})

    async def async_step_manual(self, user_input=None):
        """Manual IP fallback when auto-discovery fails."""
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
                    data={CONF_IP_ADDRESS: ip},
                )

        schema = vol.Schema({
            vol.Required(CONF_IP_ADDRESS, default=""): str,
        })

        return self.async_show_form(
            step_id="manual",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "help": "config.solutronic.manual_description"
            }
        )

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