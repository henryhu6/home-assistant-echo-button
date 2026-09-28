"""Capture one Echo Button's RFC SERVER traffic with Python and PyObjC.

Raw captures include a device identifier. Keep them in the ignored captures/
directory; do not publish them unredacted.
"""

from __future__ import annotations

import argparse
import ctypes
from pathlib import Path
import sys
import time

import Foundation
import IOBluetooth
import objc

from echo_button_protocol import EchoButtonStreamParser, battery_percent, button_state


class RFCOMMCapture(
    Foundation.NSObject,
    protocols=[objc.protocolNamed("IOBluetoothRFCOMMChannelDelegate")],
):
    """Discover the RFC SERVER SDP record and capture RFCOMM bytes."""

    def sdpQueryComplete_status_(self, device, status):
        if status != 0:
            print(f"SDP query failed: 0x{status:08x}")
            self.done = True
            return
        for record in device.services() or []:
            name = str(record.getServiceName() or "")
            if "RFC SERVER" not in name.upper():
                continue
            result, channel_id = record.getRFCOMMChannelID_(None)
            if result != 0:
                continue
            self.channel_id = channel_id
            result, channel = device.openRFCOMMChannelAsync_withChannelID_delegate_(
                None, channel_id, self
            )
            if result != 0:
                print(f"RFCOMM open failed: 0x{result:08x}")
                self.done = True
                return
            self.channel = channel
            print(f"Opening RFC SERVER on discovered channel {channel_id}...")
            return
        print("No RFC SERVER service with RFCOMM channel was found")
        self.done = True

    def rfcommChannelOpenComplete_status_(self, channel, status):
        if status != 0:
            print(f"RFCOMM connection failed: 0x{status:08x}")
            self.done = True
            return
        self.connected = True
        print("RFCOMM connected; capturing raw buffers")

    def rfcommChannelData_data_length_(self, channel, data, length):
        try:
            if not 0 < length <= 4096:
                raise ValueError(f"unexpected buffer length {length}")
            payload = ctypes.string_at(data, length)
        except (TypeError, ValueError) as error:
            print(f"Could not convert RFCOMM callback buffer: {error}")
            self.error = True
            self.done = True
            return
        self.output.write(f"RX {len(payload)} bytes: {payload.hex()}\n")
        self.output.flush()
        print(f"RX {len(payload)} bytes")
        for frame in self.parser.feed(payload):
            level = battery_percent(frame)
            if level is not None:
                print(f"Echo Button battery report: {level}% (experimental)")
            state = button_state(frame)
            if state is not None:
                print(f"Echo Button {state}")

    def rfcommChannelClosed_(self, channel):
        print("RFCOMM disconnected")
        self.done = True


def capture(address: str | None, seconds: int, output_path: Path) -> int:
    """Capture bytes from one paired Echo Button for a bounded interval."""
    devices = [
        device
        for device in IOBluetooth.IOBluetoothDevice.pairedDevices()
        if str(device.nameOrAddress()).startswith("EchoBtn")
        and (address is None or str(device.addressString()).lower().replace("-", ":") == address.lower().replace("-", ":"))
    ]
    if len(devices) != 1:
        print(f"Expected one paired Echo Button; found {len(devices)}. Set --address if needed.")
        return 1
    device = devices[0]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output:
        output.write("# Local RFCOMM capture; contains a device identifier.\n")
        probe = RFCOMMCapture.alloc().init()
        probe.channel = None
        probe.channel_id = None
        probe.connected = False
        probe.done = False
        probe.error = False
        probe.output = output
        probe.parser = EchoButtonStreamParser()
        result = device.performSDPQuery_(probe)
        if result != 0:
            print(f"SDP query could not start: 0x{result:08x}")
            return 1
        print(f"Querying services for {device.nameOrAddress()}...")
        connect_deadline = time.monotonic() + 45
        capture_deadline = None
        try:
            while not probe.done:
                if not probe.connected and time.monotonic() > connect_deadline:
                    print("SDP/RFCOMM connection timed out")
                    break
                if probe.connected and capture_deadline is None:
                    capture_deadline = time.monotonic() + seconds
                if capture_deadline is not None and time.monotonic() > capture_deadline:
                    break
                Foundation.NSRunLoop.currentRunLoop().runMode_beforeDate_(
                    Foundation.NSDefaultRunLoopMode,
                    Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.1),
                )
        except KeyboardInterrupt:
            pass
        finally:
            if probe.channel is not None:
                probe.channel.closeChannel()
    return 0 if probe.connected and not probe.error else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", help="paired Echo Button address, if multiple")
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument(
        "--output", type=Path, default=Path("captures/echo_button_python.hex")
    )
    args = parser.parse_args()
    return capture(args.address, args.seconds, args.output)


if __name__ == "__main__":
    sys.exit(main())
