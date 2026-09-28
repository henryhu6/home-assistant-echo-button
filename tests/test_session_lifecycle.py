"""Exercise socket ownership during Echo Button reconnection."""

import asyncio
import importlib
from pathlib import Path
import socket
import sys
import types
import unittest


PACKAGE = "echo_button_transport_test"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(Path(__file__).resolve().parents[1] / "custom_components" / "echo_button")]
sys.modules.setdefault(PACKAGE, package)
ButtonSession = importlib.import_module(f"{PACKAGE}.bluez").ButtonSession


class SessionLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_old_reader_does_not_close_replacement_socket(self) -> None:
        old_socket, old_peer = socket.socketpair()
        new_socket, new_peer = socket.socketpair()
        old_socket.setblocking(False)
        new_socket.setblocking(False)
        session = ButtonSession(None, "AA:BB:CC:DD:EE:FF", "Test button")
        session.socket = old_socket
        session.connected = True
        reader = asyncio.create_task(session._read())
        try:
            await asyncio.sleep(0)
            reader.cancel()
            session.socket = new_socket
            with self.assertRaises(asyncio.CancelledError):
                await reader
            self.assertIs(session.socket, new_socket)
            self.assertGreaterEqual(new_socket.fileno(), 0)
        finally:
            old_socket.close()
            old_peer.close()
            new_socket.close()
            new_peer.close()


if __name__ == "__main__":
    unittest.main()
