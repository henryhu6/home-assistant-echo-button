"""Bluetooth connection status for paired Echo Buttons."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EchoButtonConfigEntry
from .bluez import ButtonSession
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: EchoButtonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the button's connection status entity."""
    async_add_entities([EchoButtonConnection(entry.runtime_data)])


class EchoButtonConnection(BinarySensorEntity):
    """Show whether the button has an active RFCOMM connection."""

    _attr_has_entity_name = True
    _attr_name = "Connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(self, session: ButtonSession) -> None:
        self.session = session
        self._attr_unique_id = f"{session.address}_connected"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, session.address)},
            "name": session.name,
            "manufacturer": "Amazon",
            "model": "Echo Button",
        }

    @property
    def is_on(self) -> bool:
        """Return whether BlueZ currently has a socket for this button."""
        return self.session.connected

    async def async_added_to_hass(self) -> None:
        """Listen for connection changes after entity registration."""
        self.async_on_remove(self.session.subscribe(self._handle_update))

    @callback
    def _handle_update(self, kind: str, value: object) -> None:
        if kind == "connected":
            self.async_write_ha_state()
