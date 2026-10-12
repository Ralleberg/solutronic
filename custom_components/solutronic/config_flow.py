import asyncio
import inspect
import logging
from dataclasses import asdict
from urllib.parse import urlsplit

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_IP_ADDRESS,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SCAN_INTERVALS,
)
from .discovery import async_discover_inverters
from .solutronic_api import (
    SolutronicConnectionError,
    SolutronicInvalidResponseError,
    async_get_sensor_data,
    normalize_ip_address,
)
from .spp import TCP_INTERVALS, SppClient, parse_devices

_LOGGER = logging.getLogger(__name__)
_SUPPORTS_PROGRESS_TASK = (
    "progress_task"
    in inspect.signature(config_entries.ConfigFlow.async_show_progress).parameters
)
_MANUAL = "manual"


def _clean_ip(value: str) -> str:
    """Normalize and validate user input so only a raw IPv4 address remains."""
    return normalize_ip_address(value)


class SolutronicInverterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Find an inverter via UDP or configure its IP manually."""

    VERSION = 1

    def __init__(self):
        super().__init__()
        self._search_task = None
        self._discovered = []
        self._removed = False
        self._discovery_ip = None
        self._gateway_ip = None

    async def async_step_integration_discovery(self, discovery_info):
        """Offer a setup card for a device found by the startup broadcast."""
        self._discovery_ip = _clean_ip(discovery_info[CONF_IP_ADDRESS])
        await self.async_set_unique_id(self._discovery_ip)
        self._abort_if_unique_id_configured()
        self.context["title_placeholders"] = {CONF_IP_ADDRESS: self._discovery_ip}
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input=None):
        """Validate HTTP compatibility before adding an automatically found device."""
        if user_input is not None:
            return await self.async_step_manual({CONF_IP_ADDRESS: self._discovery_ip})
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={CONF_IP_ADDRESS: self._discovery_ip},
            data_schema=vol.Schema({}),
        )

    async def async_step_user(self, user_input=None):
        # Retain direct manual submissions from existing clients and flows.
        if user_input is not None and CONF_IP_ADDRESS in user_input:
            return await self.async_step_manual(user_input)
        return await self.async_step_search()

    async def async_step_search(self, user_input=None):
        """Run a short network search without blocking the setup dialog."""
        if self._search_task is None:
            self._search_task = self.hass.async_create_task(
                async_discover_inverters(self.hass)
            )
            if not _SUPPORTS_PROGRESS_TASK:
                self._search_task.add_done_callback(self._async_search_finished)

        if not self._search_task.done():
            kwargs = (
                {"progress_task": self._search_task} if _SUPPORTS_PROGRESS_TASK else {}
            )
            return self.async_show_progress(
                step_id="search", progress_action="searching", **kwargs
            )

        try:
            self._discovered = self._search_task.result()
        except Exception:
            # Adapter/socket problems must never block manual setup.
            _LOGGER.debug("Solutronic discovery failed", exc_info=True)
            self._discovered = []
        return self.async_show_progress_done(next_step_id="choose")

    @callback
    def _async_search_finished(self, task):
        """Refresh the progress dialog on HA versions without progress_task."""
        if not self._removed and not task.cancelled():
            self.hass.async_create_task(
                self.hass.config_entries.flow.async_configure(flow_id=self.flow_id)
            )

    async def async_step_choose(self, user_input=None):
        """Let the user select a candidate, or continue with manual entry."""
        if not self._discovered:
            return await self.async_step_manual()
        if user_input is not None:
            if user_input.get(CONF_IP_ADDRESS) == _MANUAL:
                return await self.async_step_manual()
            return await self.async_step_manual(user_input)

        # The label is translated by the select selector's translation_key.
        options = [item.ip_address for item in self._discovered] + [_MANUAL]
        return self.async_show_form(
            step_id="choose",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_IP_ADDRESS): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options, translation_key="discovered_inverter"
                        )
                    ),
                }
            ),
        )

    @callback
    def async_remove(self):
        """Stop discovery when the user closes the setup dialog."""
        self._removed = True
        if self._search_task is not None and not self._search_task.done():
            self._search_task.cancel()
        super().async_remove()

    async def async_step_manual(self, user_input=None):
        errors = {}
        if user_input and CONF_IP_ADDRESS in user_input:
            raw_ip = user_input[CONF_IP_ADDRESS]
            try:
                parsed = urlsplit(raw_ip if "://" in raw_ip else f"http://{raw_ip}")
                gateway_requested = parsed.port == 33330
                if gateway_requested:
                    self._gateway_ip = _clean_ip(raw_ip)
                    return await self.async_step_tcp_gateway()
            except (TypeError, ValueError, AttributeError):
                return self.async_show_form(
                    step_id="manual",
                    data_schema=vol.Schema({vol.Required(CONF_IP_ADDRESS): str}),
                    errors={CONF_IP_ADDRESS: "invalid_host"},
                )

        # If user submitted form
        if user_input and CONF_IP_ADDRESS in user_input:
            try:
                ip = _clean_ip(user_input[CONF_IP_ADDRESS])
            except ValueError:
                errors[CONF_IP_ADDRESS] = "invalid_host"
            else:
                await self.async_set_unique_id(ip)
                self._abort_if_unique_id_configured()

                try:
                    await async_get_sensor_data(ip, self.hass)
                except SolutronicInvalidResponseError:
                    errors["base"] = "invalid_response"
                except (
                    aiohttp.ClientError,
                    asyncio.TimeoutError,
                    SolutronicConnectionError,
                ):
                    _LOGGER.debug(
                        "Failed to validate Solutronic inverter at %s",
                        ip,
                        exc_info=True,
                    )
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception(
                        "Unexpected error validating the Solutronic inverter"
                    )
                    errors["base"] = "unknown"
                else:
                    return self.async_create_entry(
                        title=f"Solutronic {ip}",
                        data={CONF_IP_ADDRESS: ip},
                    )

        # Ordinary HTTP setup remains unchanged, including its error form.
        schema = vol.Schema(
            {
                vol.Required(CONF_IP_ADDRESS): str,
            }
        )

        return self.async_show_form(step_id="manual", data_schema=schema, errors=errors)

    async def async_step_tcp_gateway(self, user_input=None):
        """Explicit experimental mode; never probe SPP as an automatic fallback."""
        errors = {}
        if user_input is not None:
            try:
                ip = normalize_ip_address(user_input[CONF_IP_ADDRESS])
                master = user_input["master_address"]
                if (
                    isinstance(master, bool)
                    or not isinstance(master, int)
                    or not 1 <= master <= 65535
                ):
                    raise ValueError("Invalid master address")
                automatic = not user_input.get("devices", "").strip()
                devices = [] if automatic else parse_devices(user_input["devices"])
                if not automatic and master not in {
                    device.address for device in devices
                }:
                    raise ValueError("Include the master in the device list")
            except (ValueError, KeyError):
                errors["base"] = "invalid_gateway"
            else:
                if user_input.get("accept_experimental") is not True:
                    errors["accept_experimental"] = "experimental_required"
                else:
                    await self.async_set_unique_id(f"tcp_gateway:{ip}")
                    self._abort_if_unique_id_configured()
                    client = SppClient(
                        ip, master, [device.address for device in devices]
                    )
                    try:
                        if automatic:
                            from .spp import GatewayDevice

                            addresses = await client.async_discover()
                            devices = [
                                GatewayDevice(address, None) for address in addresses
                            ]
                            client.addresses = tuple(addresses)
                        values = await client.async_poll()
                        if not any(value is not None for value in values.values()):
                            errors["base"] = "cannot_connect"
                        else:
                            return self.async_create_entry(
                                title=f"Solutronic gateway {ip}",
                                data={
                                    CONF_IP_ADDRESS: ip,
                                    "connection_type": "tcp_gateway",
                                    "master_address": master,
                                    "auto_discover": automatic,
                                    "devices": [asdict(device) for device in devices],
                                },
                            )
                    except (OSError, asyncio.TimeoutError, ValueError):
                        errors["base"] = "cannot_connect"
                    finally:
                        await client.async_close()
        return self.async_show_form(
            step_id="tcp_gateway",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_IP_ADDRESS, default=self._gateway_ip or ""): str,
                    vol.Required("master_address"): vol.All(
                        int, vol.Range(min=1, max=65535)
                    ),
                    vol.Optional("devices", default=""): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True)
                    ),
                    vol.Required("accept_experimental", default=False): bool,
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SolutronicInverterOptionsFlow(config_entry)


class SolutronicInverterOptionsFlow(config_entries.OptionsFlow):
    """Allows changing scan interval in options."""

    def __init__(self, config_entry):
        # Keep compatibility with older HA without assigning the read-only
        # OptionsFlow.config_entry property introduced in newer releases.
        self._entry = config_entry

    async def async_step_init(self, user_input=None):
        errors = {}
        is_gateway = self._entry.data.get("connection_type") == "tcp_gateway"
        intervals = TCP_INTERVALS if is_gateway else SCAN_INTERVALS
        default_interval = 60 if is_gateway else DEFAULT_SCAN_INTERVAL
        default = self._entry.options.get(CONF_SCAN_INTERVAL, default_interval)
        if isinstance(default, bool) or default not in intervals:
            default = default_interval
        if user_input is not None:
            interval = user_input.get(CONF_SCAN_INTERVAL, default)
            if isinstance(interval, bool) or interval not in intervals:
                errors[CONF_SCAN_INTERVAL] = (
                    "invalid_gateway_interval" if is_gateway else "invalid_interval"
                )
            else:
                options = dict(self._entry.options)
                options[CONF_SCAN_INTERVAL] = interval
                if is_gateway and "discover_devices" in user_input:
                    options["discover_devices"] = user_input["discover_devices"] is True
                return self.async_create_entry(title="", data=options)

        schema = vol.Schema(
            {vol.Optional(CONF_SCAN_INTERVAL, default=default): vol.In(intervals)}
        )
        if is_gateway:
            schema = schema.extend(
                {
                    vol.Optional(
                        "discover_devices",
                        default=self._entry.options.get(
                            "discover_devices",
                            self._entry.data.get("auto_discover", False),
                        ),
                    ): bool
                }
            )

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
