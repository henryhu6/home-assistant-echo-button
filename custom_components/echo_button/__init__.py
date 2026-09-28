"""Native Home Assistant support for Classic Bluetooth Echo Buttons."""

from __future__ import annotations

import asyncio

from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .bluez import BluezManager, ButtonSession
from .const import DOMAIN

PLATFORMS = [Platform.BINARY_SENSOR, Platform.EVENT, Platform.SENSOR]
type EchoButtonConfigEntry = ConfigEntry[ButtonSession]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Prepare shared transport state."""
    hass.data[DOMAIN] = {"lock": asyncio.Lock(), "manager": None}
    return True


async def async_setup_entry(hass: HomeAssistant, entry: EchoButtonConfigEntry) -> bool:
    """Set up one paired Echo Button and its entities."""
    data = hass.data[DOMAIN]
    async with data["lock"]:
        manager: BluezManager | None = data["manager"]
        if manager is None:
            manager = BluezManager()
            try:
                await manager.start()
            except Exception as err:
                raise ConfigEntryNotReady("Cannot register the BlueZ profile") from err
            data["manager"] = manager
        session = manager.add_session(entry.data["address"], entry.data["name"])
        entry.runtime_data = session

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        async with data["lock"]:
            await manager.remove_session(session.address)
            if not manager.sessions:
                await manager.close()
                data["manager"] = None
        raise
    session.start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EchoButtonConfigEntry) -> bool:
    """Remove one button and close BlueZ when the last button is removed."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    data = hass.data[DOMAIN]
    async with data["lock"]:
        session = entry.runtime_data
        manager: BluezManager = data["manager"]
        await manager.remove_session(session.address)
        if not manager.sessions:
            await manager.close()
            data["manager"] = None
    return True
