"""Home Assistant pairing flow for Amazon Echo Buttons."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN
from .pairing import DiscoveredButton, PairingError, discover_buttons, pair_button

_LOGGER = logging.getLogger(__name__)


class EchoButtonConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Scan for and pair one button per config entry."""

    VERSION = 1

    def __init__(self) -> None:
        self.buttons: dict[str, DiscoveredButton] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Prompt for pairing mode, then scan Classic Bluetooth."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=vol.Schema({}))
        try:
            buttons = await discover_buttons()
        except PairingError as err:
            _LOGGER.warning("Echo Button discovery failed: %s", err)
            return self.async_show_form(
                step_id="user", data_schema=vol.Schema({}),
                errors={"base": "cannot_scan"},
            )
        self.buttons = {button.address: button for button in buttons}
        if not self.buttons:
            return self.async_show_form(
                step_id="user", data_schema=vol.Schema({}),
                errors={"base": "no_buttons"},
            )
        return await self.async_step_select()

    async def async_step_select(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select a found button and pair it if needed."""
        choices = {
            address: f"{button.name} ({address})"
            + (" — already paired" if button.paired else "")
            for address, button in self.buttons.items()
        }
        schema = vol.Schema({vol.Required("address"): vol.In(choices)})
        if user_input is None:
            return self.async_show_form(step_id="select", data_schema=schema)
        address = user_input["address"]
        button = self.buttons[address]
        await self.async_set_unique_id(address)
        self._abort_if_unique_id_configured()
        try:
            await pair_button(button)
        except PairingError as err:
            _LOGGER.warning("Echo Button pairing failed: %s", err)
            return self.async_show_form(
                step_id="select", data_schema=schema,
                errors={"base": "cannot_pair"},
            )
        return self.async_create_entry(
            title=button.name,
            data={"address": button.address, "name": button.name},
        )
