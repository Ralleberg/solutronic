import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import socket
import ipaddress
import requests
from .const import DOMAIN

CONF_HOST = "host"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 5
DEFAULT_TIMEOUT = 2


def get_local_subnet():
    """Find the local subnet based on the host's IP address."""
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        # Assume a subnet mask of 255.255.255.0 (CIDR /24)
        ip_network = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
        return ip_network
    except Exception as e:
        return None


def find_solutronic_devices(timeout=DEFAULT_TIMEOUT):
    """Scan the local subnet for Solutronic devices."""
    devices = []
    subnet = get_local_subnet()
    if not subnet:
        return devices

    for ip in subnet.hosts():
        try:
            response = requests.get(f"http://{ip}", timeout=timeout)
            if "solutronic" in response.text.lower():
                devices.append(str(ip))
        except (requests.ConnectionError, requests.Timeout):
            continue

    return devices


class SolutronicConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solutronic."""

    VERSION = 1

    def __init__(self):
        self.discovered_devices = []

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            return self.async_create_entry(title="Solutronic", data=user_input)

        # Scan the network for devices
        self.discovered_devices = await self.hass.async_add_executor_job(find_solutronic_devices)

        if self.discovered_devices:
            # If devices are found, allow user to select one
            return self.async_step_select_device()

        # If no devices found, prompt manual input
        return self.async_step_manual_input()

    async def async_step_select_device(self, user_input=None) -> FlowResult:
        """Handle device selection from discovered devices."""
        if user_input is not None:
            return self.async_create_entry(title="Solutronic", data=user_input)

        return self.async_show_form(
            step_id="select_device",
            data_schema=vol.Schema({vol.Required(CONF_HOST): vol.In(self.discovered_devices)}),
        )

    async def async_step_manual_input(self, user_input=None) -> FlowResult:
        """Handle manual IP input."""
        errors = {}

        if user_input is not None:
            # Validate the IP address
            try:
                requests.get(f"http://{user_input[CONF_HOST]}", timeout=DEFAULT_TIMEOUT)
                return self.async_create_entry(title="Solutronic", data=user_input)
            except requests.RequestException:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="manual_input",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return SolutronicOptionsFlowHandler(config_entry)


class SolutronicOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Solutronic."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Manage the options for the integration."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_SCAN_INTERVAL, default=self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): int,
                }
            ),
        )
