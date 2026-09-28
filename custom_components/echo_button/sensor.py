"""Experimental Echo Button battery sensor."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EchoButtonConfigEntry
from .bluez import ButtonSession
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: EchoButtonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the button's battery reading."""
    async_add_entities([EchoButtonBattery(entry.runtime_data)])


class EchoButtonBattery(SensorEntity):
    """Show the apparent percentage reported when the button connects."""

    _attr_has_entity_name = True
    _attr_name = "Battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(self, session: ButtonSession) -> None:
        self.session = session
        self._attr_unique_id = f"{session.address}_battery"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, session.address)},
            "name": session.name,
            "manufacturer": "Amazon",
            "model": "Echo Button",
        }

    @property
    def native_value(self) -> int | None:
        """Return the last experimentally decoded battery reading."""
        return self.session.battery_level

    async def async_added_to_hass(self) -> None:
        """Subscribe after Home Assistant has registered this entity."""
        self.async_on_remove(self.session.subscribe(self._handle_update))

    @callback
    def _handle_update(self, kind: str, value: object) -> None:
        if kind == "battery":
            self.async_write_ha_state()
