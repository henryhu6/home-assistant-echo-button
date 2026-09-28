"""Small protocol observations from one Echo Button, kept independent of macOS.

The battery field was identified experimentally on one button: its old AAA
cells reported 64, 61, and 62 across connections, fresh cells reported 100,
and a third pair reported 63. The two trailer bytes are the packet checksum.
"""

from __future__ import annotations

import time


STALE_PRESS_SECONDS = 2.0


def packet_checksum(frame: bytes) -> int | None:
    """Calculate the checksum of an unescaped Classic gadget packet."""
    if len(frame) < 7 or frame[0] != 0xF0 or frame[-1] != 0xF1:
        return None
    return (frame[1] + frame[2] + sum(frame[4:-3])) & 0xFFFF


def valid_packet_checksum(frame: bytes) -> bool:
    """Check the two-byte big-endian trailer against the packet contents."""
    calculated = packet_checksum(frame)
    return calculated is not None and calculated == int.from_bytes(frame[-3:-1], "big")


def encode_packet(payload: bytes, sequence: int, command: int = 0x02) -> bytes:
    """Encode the verified Classic gadget packet envelope for future commands.

    This does not define any button-specific command, including LED control.
    """
    if not 0 <= command <= 0xFF or not 0 <= sequence <= 0xFF:
        raise ValueError("command and sequence must be bytes")
    if sequence in (0xF0, 0xF1, 0xF2):
        raise ValueError("reserved sequence byte")
    checksum = (command + sum(payload)) & 0xFFFF
    wire = bytearray((0xF0, command, 0x00, sequence))
    for value in payload + checksum.to_bytes(2, "big"):
        if value in (0xF0, 0xF1, 0xF2):
            wire.extend((0xF2, 0xF2 ^ value))
        else:
            wire.append(value)
    wire.append(0xF1)
    return bytes(wire)


class EchoButtonStreamParser:
    """Extract checksummed packets from arbitrary RFCOMM byte chunks."""

    def __init__(self) -> None:
        self._pending = bytearray()
        self._escaped = False

    def feed(self, chunk: bytes) -> list[bytes]:
        """Return complete decoded frames, retaining any incomplete tail."""
        frames: list[bytes] = []
        for value in chunk:
            if not self._pending:
                if value == 0xF0:
                    self._pending.append(value)
                continue
            if self._escaped:
                self._pending.append(0xF2 ^ value)
                self._escaped = False
            elif value == 0xF2:
                self._escaped = True
            elif value == 0xF0:
                self._pending = bytearray((value,))
            elif value == 0xF1:
                self._pending.append(value)
                frame = bytes(self._pending)
                if valid_packet_checksum(frame):
                    frames.append(frame)
                self._pending.clear()
            else:
                self._pending.append(value)
            if len(self._pending) > 4096:
                self._pending.clear()
                self._escaped = False
        return frames


def battery_percent(frame: bytes) -> int | None:
    """Extract the apparent battery percentage from a startup status frame.

    The 32-byte status frame has a distinct prefix and payload shape. Its byte
    27 changed with a controlled battery replacement. The meaning should be
    checked on another button before treating it as a fully documented field.
    """
    if len(frame) != 32:
        return None
    if frame[:3] != b"\xf0\x02\x00":
        return None
    if frame[4:8] != b"\x01\x03\x01\x10":
        return None
    if frame[24:27] != b"\x01\x03\x00" or frame[28] != 0x03:
        return None
    if frame[-1] != 0xF1:
        return None
    value = frame[27]
    return value if value <= 100 else None


def button_state(frame: bytes) -> str | None:
    """Return a press/release state for an observed 40-byte event frame."""
    if len(frame) != 40:
        return None
    if frame[:3] != b"\xf0\x02\x00":
        return None
    if frame[4:8] != b"\x01\x01\x01\x10":
        return None
    if frame[24:29] != b"\x01\x0b\x00\x00\x01" or frame[-1] != 0xF1:
        return None
    return {0x02: "pressed", 0x03: "released"}.get(frame[29])


class ButtonTransitionTracker:
    """Emit each physical state transition once within one connection."""

    def __init__(self) -> None:
        self.pressed = False
        self.last_press_at: float | None = None

    def observe(self, state: str | None, now: float | None = None) -> str | None:
        """Ignore rapid duplicates, but recover from an unpaired old press."""
        if state is None:
            return None
        if now is None:
            now = time.monotonic()
        if state == "pressed":
            new_press = (
                not self.pressed
                or self.last_press_at is None
                or now - self.last_press_at >= STALE_PRESS_SECONDS
            )
            self.pressed = True
            self.last_press_at = now
            return state if new_press else None
        if state == "released" and self.pressed:
            self.pressed = False
            self.last_press_at = None
            return state
        return None
