"""Echo Button press events shown as a Home Assistant event entity."""

from __future__ import annotations

import logging

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EchoButtonConfigEntry
from .bluez import ButtonSession
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: EchoButtonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the button's physical event entity."""
    async_add_entities([EchoButtonEvent(entry.runtime_data)])


class EchoButtonEvent(EventEntity):
    """Represent press and release events from one Echo Button."""

    _attr_has_entity_name = True
    _attr_name = "Action"
    _attr_device_class = EventDeviceClass.BUTTON
    _attr_event_types = ["press_start", "press_end"]
    _attr_should_poll = False

    def __init__(self, session: ButtonSession) -> None:
        self.session = session
        self._attr_unique_id = f"{session.address}_button"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, session.address)},
            "name": session.name,
            "manufacturer": "Amazon",
            "model": "Echo Button",
        }

    async def async_added_to_hass(self) -> None:
        """Listen for decoded button events after entity registration."""
        self.async_on_remove(self.session.subscribe(self._handle_update))

    @callback
    def _handle_update(self, kind: str, value: object) -> None:
        if kind == "button":
            event_type = "press_start" if value == "pressed" else "press_end"
            _LOGGER.debug("Echo Button %s event=%s", self.session.name, event_type)
            self._trigger_event(event_type)
            self.async_write_ha_state()
