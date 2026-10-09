import asyncio
import inspect
import logging

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

        # Show input form
        schema = vol.Schema(
            {
                vol.Required(CONF_IP_ADDRESS): str,
            }
        )

        return self.async_show_form(step_id="manual", data_schema=schema, errors=errors)

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
        default = self._entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        if isinstance(default, bool) or default not in SCAN_INTERVALS:
            default = DEFAULT_SCAN_INTERVAL
        if user_input is not None:
            interval = user_input.get(CONF_SCAN_INTERVAL, default)
            if isinstance(interval, bool) or interval not in SCAN_INTERVALS:
                errors[CONF_SCAN_INTERVAL] = "invalid_interval"
            else:
                options = dict(self._entry.options)
                options[CONF_SCAN_INTERVAL] = interval
                return self.async_create_entry(title="", data=options)

        schema = vol.Schema(
            {vol.Optional(CONF_SCAN_INTERVAL, default=default): vol.In(SCAN_INTERVALS)}
        )

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
