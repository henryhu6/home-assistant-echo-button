"""Keep BlueZ bus failures inside the pairing flow's expected error type."""

import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


PACKAGE = "echo_button_transport_test"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(Path(__file__).resolve().parents[1] / "custom_components" / "echo_button")]
sys.modules.setdefault(PACKAGE, package)
pairing = importlib.import_module(f"{PACKAGE}.pairing")


class FailingBus:
    async def connect(self) -> None:
        raise OSError("system D-Bus unavailable")

    async def call(self, message: object) -> None:
        raise OSError("system D-Bus disconnected")


class RecordingBus:
    def __init__(self) -> None:
        self.exported = False
        self.unexported = False
        self.disconnected = False

    def export(self, path: str, agent: object) -> None:
        self.exported = True

    def unexport(self, path: str, agent: object) -> None:
        self.unexported = True

    def disconnect(self) -> None:
        self.disconnected = True


class PairingErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_call_wraps_transport_failure(self) -> None:
        with self.assertRaises(pairing.PairingError):
            await pairing._call(FailingBus(), "/org/bluez", "org.bluez.Adapter1", "StartDiscovery")

    async def test_discovery_wraps_bus_connection_failure(self) -> None:
        with patch.object(pairing, "MessageBus", return_value=FailingBus()):
            with self.assertRaises(pairing.PairingError):
                await pairing.discover_buttons(seconds=0)

    async def test_pairing_wraps_bus_connection_failure(self) -> None:
        button = pairing.DiscoveredButton("/org/bluez/device", "AA:BB:CC:DD:EE:FF", "EchoBtn", False)
        with patch.object(pairing, "MessageBus", return_value=FailingBus()):
            with self.assertRaises(pairing.PairingError):
                await pairing.pair_button(button)

    async def test_late_bond_completes_after_pair_error(self) -> None:
        button = pairing.DiscoveredButton("/org/bluez/device", "AA:BB:CC:DD:EE:FF", "EchoBtn", False)
        bus = RecordingBus()
        unpaired = {button.path: {"org.bluez.Device1": {
            "Address": pairing.Variant("s", button.address),
            "Paired": pairing.Variant("b", False),
        }}}
        paired = {button.path: {"org.bluez.Device1": {
            "Address": pairing.Variant("s", button.address),
            "Paired": pairing.Variant("b", True),
            "UUIDs": pairing.Variant("as", [pairing.RFC_SERVER_UUID]),
        }}}
        calls = []

        async def call(bus: object, path: str, interface: str, member: str, *args: object) -> None:
            calls.append(member)
            if member == "Pair":
                raise pairing.PairingError("AuthenticationFailed")

        with patch.object(pairing, "_open_bus", new=AsyncMock(return_value=bus)):
            with patch.object(pairing, "_managed_objects", new=AsyncMock(side_effect=[unpaired, paired, paired])):
                with patch.object(pairing, "_call", new=call):
                    await pairing.pair_button(button)

        self.assertTrue(bus.exported)
        self.assertTrue(bus.unexported)
        self.assertTrue(bus.disconnected)
        self.assertEqual(calls, ["RegisterAgent", "Pair", "Set", "UnregisterAgent"])


if __name__ == "__main__":
    unittest.main()
