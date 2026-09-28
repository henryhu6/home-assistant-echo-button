"""Discover and pair Echo Buttons through the host's BlueZ D-Bus API."""

import asyncio
from dataclasses import dataclass
import logging

from dbus_fast import BusType, Message, MessageType, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.errors import DBusError
from dbus_fast.service import ServiceInterface, method

from .const import RFC_SERVER_UUID

BLUEZ = "org.bluez"
AGENT_PATH = "/org/homeassistant/echo_button/pairing_agent"
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiscoveredButton:
    """One Echo Button found in BlueZ's object tree."""

    path: str
    address: str
    name: str
    paired: bool


class PairingError(Exception):
    """BlueZ could not find or pair the requested button."""


async def _open_bus() -> MessageBus:
    """Connect to BlueZ or report a setup-flow error."""
    try:
        return await MessageBus(bus_type=BusType.SYSTEM).connect()
    except (DBusError, OSError) as err:
        raise PairingError("Cannot access the host system D-Bus") from err


class EchoButtonAgent(ServiceInterface):
    """Accept authorization only for the button selected in the UI."""

    def __init__(self, device_path: str) -> None:
        super().__init__("org.bluez.Agent1")
        self._device_path = device_path

    def _verify(self, device: str) -> None:
        if device != self._device_path:
            raise DBusError("org.bluez.Error.Rejected", "Unexpected device")

    @method()
    def Release(self) -> None:
        """BlueZ released the agent."""

    @method()
    def RequestPinCode(self, device: "o") -> "s":
        """Echo Buttons use secure simple pairing, not a PIN."""
        self._verify(device)
        raise DBusError("org.bluez.Error.Rejected", "PIN pairing is unsupported")

    @method()
    def RequestPasskey(self, device: "o") -> "u":
        """Echo Buttons do not have a passkey input."""
        self._verify(device)
        raise DBusError("org.bluez.Error.Rejected", "Passkey pairing is unsupported")

    @method()
    def DisplayPinCode(self, device: "o", pincode: "s") -> None:
        """A display request is not expected for this button."""
        self._verify(device)

    @method()
    def DisplayPasskey(self, device: "o", passkey: "u", entered: "q") -> None:
        """A display request is not expected for this button."""
        self._verify(device)

    @method()
    def RequestConfirmation(self, device: "o", passkey: "u") -> None:
        """Confirm the device the user selected to pair."""
        self._verify(device)

    @method()
    def RequestAuthorization(self, device: "o") -> None:
        """Authorize the selected button."""
        self._verify(device)

    @method()
    def AuthorizeService(self, device: "o", uuid: "s") -> None:
        """Authorize services on the selected button during pairing."""
        self._verify(device)

    @method()
    def Cancel(self) -> None:
        """BlueZ cancelled the pairing request."""


async def _call(
    bus: MessageBus,
    path: str,
    interface: str,
    member: str,
    signature: str = "",
    body: list | None = None,
) -> Message:
    try:
        reply = await bus.call(
            Message(
                destination=BLUEZ,
                path=path,
                interface=interface,
                member=member,
                signature=signature,
                body=body or [],
            )
        )
    except (DBusError, OSError) as err:
        raise PairingError(f"{member}: system D-Bus call failed") from err
    if reply is None:
        raise PairingError(f"{member}: no D-Bus reply")
    if reply.message_type == MessageType.ERROR:
        raise PairingError(f"{member}: {reply.error_name}: {reply.body}")
    return reply


def _buttons(objects: dict) -> list[DiscoveredButton]:
    found = []
    for path, interfaces in objects.items():
        props = interfaces.get("org.bluez.Device1")
        if props is None:
            continue
        name = props.get("Name") or props.get("Alias")
        if name is None or not str(name.value).startswith("EchoBtn"):
            continue
        address = props.get("Address")
        if address is None:
            continue
        paired = props.get("Paired")
        found.append(
            DiscoveredButton(
                path, str(address.value).upper(), str(name.value),
                bool(paired.value) if paired else False,
            )
        )
    return sorted(found, key=lambda item: (not item.paired, item.name, item.address))


async def _managed_objects(bus: MessageBus) -> dict:
    reply = await _call(bus, "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects")
    return reply.body[0]


async def discover_buttons(seconds: int = 10) -> list[DiscoveredButton]:
    """Scan only Classic Bluetooth and return named Echo Buttons."""
    bus = await _open_bus()
    try:
        objects = await _managed_objects(bus)
        adapters = [
            path for path, interfaces in objects.items()
            if interfaces.get("org.bluez.Adapter1", {}).get("Powered", Variant("b", False)).value
        ]
        if not adapters:
            raise PairingError("No powered Bluetooth adapter is available")
        adapter = adapters[0]
        await _call(
            bus, adapter, "org.bluez.Adapter1", "SetDiscoveryFilter", "a{sv}",
            [{"Transport": Variant("s", "bredr"), "Pattern": Variant("s", "EchoBtn")}],
        )
        started = False
        try:
            await _call(bus, adapter, "org.bluez.Adapter1", "StartDiscovery")
            started = True
            await asyncio.sleep(seconds)
        finally:
            if started:
                await _call(bus, adapter, "org.bluez.Adapter1", "StopDiscovery")
        return _buttons(await _managed_objects(bus))
    finally:
        bus.disconnect()


async def pair_button(button: DiscoveredButton) -> None:
    """Pair and trust a selected button, checking its RFCOMM service."""
    bus = await _open_bus()
    agent = EchoButtonAgent(button.path)
    registered = False
    try:
        objects = await _managed_objects(bus)
        props = objects.get(button.path, {}).get("org.bluez.Device1")
        if props is None or str(props.get("Address", Variant("s", "")).value).upper() != button.address:
            raise PairingError("The selected button is no longer available; scan again")
        if not bool(props.get("Paired", Variant("b", False)).value):
            bus.export(AGENT_PATH, agent)
            await _call(
                bus, "/org/bluez", "org.bluez.AgentManager1", "RegisterAgent",
                "os", [AGENT_PATH, "NoInputNoOutput"],
            )
            registered = True
            try:
                await _call(bus, button.path, "org.bluez.Device1", "Pair")
            except PairingError:
                # BlueZ can report an authentication error while the bond is
                # completing. Accept only an actual bond on the selected path.
                for attempt in range(6):
                    refreshed = (await _managed_objects(bus)).get(button.path, {}).get(
                        "org.bluez.Device1", {}
                    )
                    if bool(refreshed.get("Paired", Variant("b", False)).value):
                        _LOGGER.debug(
                            "BlueZ reported a pairing error after %s became paired",
                            button.name,
                        )
                        break
                    if attempt < 5:
                        await asyncio.sleep(0.5)
                else:
                    raise
        await _call(
            bus, button.path, "org.freedesktop.DBus.Properties", "Set", "ssv",
            ["org.bluez.Device1", "Trusted", Variant("b", True)],
        )
        refreshed = (await _managed_objects(bus)).get(button.path, {}).get("org.bluez.Device1", {})
        uuids = [str(uuid).lower() for uuid in refreshed.get("UUIDs", Variant("as", [])).value]
        if RFC_SERVER_UUID not in uuids:
            raise PairingError("Paired button did not expose the required RFCOMM service")
    finally:
        if registered:
            try:
                await _call(
                    bus, "/org/bluez", "org.bluez.AgentManager1", "UnregisterAgent",
                    "o", [AGENT_PATH],
                )
            finally:
                bus.unexport(AGENT_PATH, agent)
        bus.disconnect()
