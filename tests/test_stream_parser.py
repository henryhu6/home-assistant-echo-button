"""Check RFCOMM stream framing at read boundaries using anonymized frames."""

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "echo_button"))

from protocol import (
    EchoButtonStreamParser,
    battery_percent,
    button_state,
    encode_packet,
    packet_checksum,
    valid_packet_checksum,
)


def frame(kind: int, length: int, state: int = 0) -> bytes:
    data = bytearray(length)
    data[:8] = bytes((0xF0, 0x02, 0x00, 0x01, 0x01, kind, 0x01, 0x10))
    data[8:24] = b"X" * 16
    data[-1] = 0xF1
    if kind == 0x03:
        data[24:29] = bytes((0x01, 0x03, 0x00, 63, 0x03))
    if kind == 0x01:
        data[24:30] = bytes((0x01, 0x0B, 0x00, 0x00, 0x01, state))
    data[-3:-1] = packet_checksum(data).to_bytes(2, "big")
    return bytes(data)


class StreamParserTests(unittest.TestCase):
    def test_split_and_combined_reads(self) -> None:
        expected = [
            frame(0x04, 54),
            frame(0x03, 32),
            frame(0x01, 40, 0x02),
            frame(0x01, 40, 0x03),
        ]
        stream = b"".join(expected)
        self.assertEqual(EchoButtonStreamParser().feed(stream), expected)
        for cut in range(1, len(stream)):
            parser = EchoButtonStreamParser()
            self.assertEqual(parser.feed(stream[:cut]) + parser.feed(stream[cut:]), expected)
        parser = EchoButtonStreamParser()
        self.assertEqual(
            [item for byte in stream for item in parser.feed(bytes((byte,)))],
            expected,
        )
        self.assertEqual(battery_percent(expected[1]), 63)
        self.assertEqual(button_state(expected[2]), "pressed")
        self.assertEqual(button_state(expected[3]), "released")

    def test_discard_noise_and_recover(self) -> None:
        event = frame(0x01, 40, 0x02)
        parser = EchoButtonStreamParser()
        self.assertEqual(parser.feed(b"noise\xf0\x02"), [])
        self.assertEqual(parser.feed(b"\x00\x00" + event), [event])

    def test_corrupted_frame_is_ignored(self) -> None:
        event = frame(0x01, 40, 0x02)
        damaged = bytearray(event)
        damaged[29] = 0x03
        self.assertFalse(valid_packet_checksum(damaged))
        self.assertEqual(EchoButtonStreamParser().feed(bytes(damaged) + event), [event])

    def test_escaped_payload_across_reads(self) -> None:
        event = bytearray(frame(0x01, 40, 0x02))
        event[30] = 0xF0
        event[-3:-1] = packet_checksum(event).to_bytes(2, "big")
        wire = event[:4] + bytearray().join(
            bytes((0xF2, 0xF2 ^ byte)) if byte in (0xF0, 0xF1, 0xF2)
            else bytes((byte,))
            for byte in event[4:-1]
        ) + bytes((0xF1,))
        self.assertGreater(len(wire), len(event))
        for cut in range(1, len(wire)):
            parser = EchoButtonStreamParser()
            self.assertEqual(parser.feed(wire[:cut]) + parser.feed(wire[cut:]), [bytes(event)])

    def test_encoder_matches_captured_packet_envelope(self) -> None:
        event = frame(0x01, 40, 0x02)
        self.assertEqual(encode_packet(event[4:-3], event[3]), event)
        payload = bytes((0xF0, 0xF1, 0xF2))
        encoded = encode_packet(payload, 1)
        self.assertEqual(EchoButtonStreamParser().feed(encoded)[0][4:-3], payload)


if __name__ == "__main__":
    unittest.main()
