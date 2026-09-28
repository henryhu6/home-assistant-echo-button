"""Shared BlueZ RFCOMM transport for paired Echo Buttons."""

import asyncio
import logging
import os
import socket
from collections.abc import Callable
from typing import Any

from dbus_fast import BusType, Message, MessageType, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.errors import DBusError
from dbus_fast.service import ServiceInterface, method

from .const import PROFILE_PATH, RFC_SERVER_UUID
from .protocol import (
    ButtonTransitionTracker,
    EchoButtonStreamParser,
    battery_percent,
    button_state,
)

_LOGGER = logging.getLogger(__name__)
BLUEZ = "org.bluez"
Listener = Callable[[str, Any], None]


class EchoButtonProfile(ServiceInterface):
    """Receive RFCOMM socket descriptors from BlueZ."""

    def __init__(self, manager: "BluezManager") -> None:
        super().__init__("org.bluez.Profile1")
        self.manager = manager

    @method()
    def Release(self) -> None:
        """BlueZ released the profile."""
        _LOGGER.warning("BlueZ released the Echo Button profile")
        self.manager.registered = False

    @method()
    def NewConnection(self, device: "o", fd: "h", fd_properties: "a{sv}") -> None:
        """Route the incoming socket to its button."""
        self.manager.new_connection(device, fd)

    @method()
    def RequestDisconnection(self, device: "o") -> None:
        """Close a socket on BlueZ's request."""
        self.manager.request_disconnection(device)


class ButtonSession:
    """Connect and decode one paired Echo Button."""

    def __init__(self, manager: "BluezManager", address: str, name: str) -> None:
        self.manager = manager
        self.address = address.upper()
        self.name = name
        self.device_path: str | None = None
        self.connected = False
        self.battery_level: int | None = None
        self.socket: socket.socket | None = None
        self.parser = EchoButtonStreamParser()
        self.transitions = ButtonTransitionTracker()
        self.listeners: set[Listener] = set()
        self.connected_event = asyncio.Event()
        self.disconnected_event = asyncio.Event()
        self.last_connect_error: str | None = None
        self.stopped = False
        self.connect_task: asyncio.Task[None] | None = None
        self.read_task: asyncio.Task[None] | None = None

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """Subscribe to button, battery, and connection updates."""
        self.listeners.add(listener)
        return lambda: self.listeners.discard(listener)

    def emit(self, kind: str, value: Any) -> None:
        """Notify listeners without letting one callback break transport."""
        for listener in tuple(self.listeners):
            try:
                listener(kind, value)
            except Exception:
                _LOGGER.exception("Echo Button update listener failed")

    def start(self) -> None:
        """Start connection attempts after entities have subscribed."""
        self.connect_task = asyncio.create_task(
            self._connect_loop(), name=f"echo_button_connect_{self.address}"
        )

    async def stop(self) -> None:
        """Stop retries and close the active socket."""
        self.stopped = True
        if self.connect_task is not None:
            self.connect_task.cancel()
            try:
                await self.connect_task
            except asyncio.CancelledError:
                pass
            self.connect_task = None
        self._close_socket()
        if self.read_task is not None:
            self.read_task.cancel()
            try:
                await self.read_task
            except asyncio.CancelledError:
                pass
            self.read_task = None

    async def _connect_loop(self) -> None:
        while not self.stopped:
            try:
                self.connected_event.clear()
                self.disconnected_event.clear()
                self.device_path = await self.manager.find_device(self.address)
                if self.device_path is None:
                    raise RuntimeError("Paired button is absent from BlueZ")
                if not self.connected:
                    await self.manager.call(
                        self.device_path, "org.bluez.Device1", "ConnectProfile",
                        "s", [RFC_SERVER_UUID],
                    )
                if self.connected:
                    self.connected_event.set()
                await asyncio.wait_for(self.connected_event.wait(), timeout=15)
                await self.disconnected_event.wait()
            except asyncio.CancelledError:
                raise
            except Exception as err:
                if self.connected:
                    await self.disconnected_event.wait()
                else:
                    error = str(err)
                    if error != self.last_connect_error:
                        _LOGGER.warning("Cannot connect to Echo Button %s: %s", self.name, err)
                        self.last_connect_error = error
                    else:
                        _LOGGER.debug("Echo Button %s still unavailable: %s", self.name, err)
            if not self.stopped:
                await asyncio.sleep(2)

    def new_connection(self, device: str, fd: int) -> None:
        """Take ownership of an RFCOMM socket passed by BlueZ."""
        if device != self.device_path or self.socket is not None:
            os.close(fd)
            raise DBusError("org.bluez.Error.Rejected", "Unexpected connection")
        self.socket = socket.socket(fileno=fd)
        self.socket.setblocking(False)
        self.parser = EchoButtonStreamParser()
        self.transitions = ButtonTransitionTracker()
        self.connected = True
        self.last_connect_error = None
        self.connected_event.set()
        self.emit("connected", True)
        _LOGGER.info("Echo Button %s connected", self.name)
        self.read_task = asyncio.create_task(
            self._read(), name=f"echo_button_read_{self.address}"
        )

    def request_disconnection(self) -> None:
        """Close the socket on a BlueZ request."""
        self._close_socket()
        self.disconnected_event.set()

    async def _read(self) -> None:
        sock = self.socket
        if sock is None:
            return
        try:
            loop = asyncio.get_running_loop()
            while True:
                data = await loop.sock_recv(sock, 4096)
                if not data:
                    return
                for frame in self.parser.feed(data):
                    raw_state = button_state(frame)
                    state = self.transitions.observe(raw_state)
                    if raw_state is not None:
                        _LOGGER.debug(
                            "Echo Button %s frame sequence=%d state=%s emitted=%s",
                            self.name, frame[3], raw_state, state is not None,
                        )
                    if state is not None:
                        self.emit("button", state)
                    level = battery_percent(frame)
                    if level is not None:
                        self.battery_level = level
                        self.emit("battery", level)
        except asyncio.CancelledError:
            raise
        except OSError as err:
            _LOGGER.debug("Echo Button %s socket closed: %s", self.name, err)
        finally:
            if self.socket is sock:
                self._close_socket()
                self.disconnected_event.set()
            else:
                sock.close()

    def _close_socket(self) -> None:
        sock = self.socket
        self.socket = None
        if sock is not None:
            sock.close()
        if self.connected:
            self.connected = False
            self.emit("connected", False)
            _LOGGER.info("Echo Button %s disconnected", self.name)


class BluezManager:
    """Own one BlueZ client profile shared by every configured button."""

    def __init__(self) -> None:
        self.bus: MessageBus | None = None
        self.profile: EchoButtonProfile | None = None
        self.registered = False
        self.sessions: dict[str, ButtonSession] = {}

    async def start(self) -> None:
        """Connect to the host D-Bus and register the RFCOMM profile."""
        self.bus = await MessageBus(
            bus_type=BusType.SYSTEM, negotiate_unix_fd=True
        ).connect()
        self.profile = EchoButtonProfile(self)
        self.bus.export(PROFILE_PATH, self.profile)
        try:
            await self.call(
                "/org/bluez", "org.bluez.ProfileManager1", "RegisterProfile",
                "osa{sv}", [
                    PROFILE_PATH, RFC_SERVER_UUID,
                    {
                        "Name": Variant("s", "Echo Button"),
                        "Role": Variant("s", "client"),
                        "AutoConnect": Variant("b", True),
                        "RequireAuthentication": Variant("b", True),
                    },
                ],
            )
            self.registered = True
        except Exception:
            self.bus.unexport(PROFILE_PATH, self.profile)
            self.bus.disconnect()
            self.bus = None
            raise

    async def close(self) -> None:
        """Stop all sessions and unregister the profile."""
        for address in tuple(self.sessions):
            await self.remove_session(address)
        if self.bus is None:
            return
        if self.registered:
            try:
                await self.call(
                    "/org/bluez", "org.bluez.ProfileManager1", "UnregisterProfile",
                    "o", [PROFILE_PATH],
                )
            except Exception:
                _LOGGER.exception("Could not unregister the Echo Button profile")
        if self.profile is not None:
            self.bus.unexport(PROFILE_PATH, self.profile)
        self.bus.disconnect()
        self.bus = None

    def add_session(self, address: str, name: str) -> ButtonSession:
        """Create one session for a configured button."""
        address = address.upper()
        if address in self.sessions:
            raise RuntimeError(f"Button {address} is already configured")
        session = ButtonSession(self, address, name)
        self.sessions[address] = session
        return session

    async def remove_session(self, address: str) -> None:
        """Remove a button session."""
        session = self.sessions.pop(address.upper(), None)
        if session is not None:
            await session.stop()

    def new_connection(self, device: str, fd: int) -> None:
        """Route a BlueZ connection to its configured button."""
        for session in self.sessions.values():
            if session.device_path == device:
                session.new_connection(device, fd)
                return
        os.close(fd)
        raise DBusError("org.bluez.Error.Rejected", "Unconfigured Echo Button")

    def request_disconnection(self, device: str) -> None:
        """Route a BlueZ disconnection to its button."""
        for session in self.sessions.values():
            if session.device_path == device:
                session.request_disconnection()
                return

    async def find_device(self, address: str) -> str | None:
        """Find a paired BlueZ device with the required service."""
        reply = await self.call(
            "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects"
        )
        for path, interfaces in reply.body[0].items():
            device = interfaces.get("org.bluez.Device1")
            if device is None:
                continue
            if str(device.get("Address", Variant("s", "")).value).upper() != address:
                continue
            if not device.get("Paired", Variant("b", False)).value:
                return None
            uuids = [str(item).lower() for item in device.get("UUIDs", Variant("as", [])).value]
            return path if RFC_SERVER_UUID in uuids else None
        return None

    async def call(
        self, path: str, interface: str, member: str,
        signature: str = "", body: list | None = None,
    ) -> Message:
        """Call BlueZ and raise a readable error for failed replies."""
        if self.bus is None:
            raise RuntimeError("System D-Bus is disconnected")
        reply = await self.bus.call(
            Message(
                destination=BLUEZ, path=path, interface=interface,
                member=member, signature=signature, body=body or [],
            )
        )
        if reply is None:
            raise RuntimeError(f"{member}: no D-Bus reply")
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError(f"{member}: {reply.error_name}: {reply.body}")
        return reply
