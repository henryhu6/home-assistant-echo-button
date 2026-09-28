"""Check whether an Echo Button exposes battery status to macOS or BLE.

Run with the project's Python virtual environment and PyObjC installed. The
Bluetooth Classic RFCOMM capture is a separate protocol and has no verified
battery field yet.
"""

from __future__ import annotations

import argparse
import json
import plistlib
import subprocess
import sys
import time

import CoreBluetooth
import Foundation
import IOBluetooth


def _system_profiler_buttons() -> dict[str, dict]:
    """Read only Echo Button entries from macOS's Bluetooth inventory."""
    result = subprocess.run(
        ["system_profiler", "SPBluetoothDataType", "-json"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    report = json.loads(result.stdout)
    found: dict[str, dict] = {}
    for adapter in report.get("SPBluetoothDataType", []):
        for group in ("device_connected", "device_not_connected"):
            for entry in adapter.get(group, []):
                for name, details in entry.items():
                    if name.startswith("EchoBtn"):
                        found[name] = details
    return found


def _hid_battery_fields() -> dict[str, dict]:
    """Inspect macOS HID records for battery data without dumping device IDs."""
    result = subprocess.run(
        ["ioreg", "-a", "-r", "-c", "IOHIDDevice"],
        check=True,
        capture_output=True,
        timeout=30,
    )
    records = plistlib.loads(result.stdout)
    found: dict[str, dict] = {}

    def visit(value: object) -> None:
        if isinstance(value, dict):
            name = value.get("Product")
            if isinstance(name, str) and name.startswith("EchoBtn"):
                found[name] = {
                    key: item
                    for key, item in value.items()
                    if "battery" in key.lower()
                    or "charge" in key.lower()
                    or "voltage" in key.lower()
                }
            for item in value.values():
                if isinstance(item, (dict, list)):
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(records)
    return found


def mac_status() -> int:
    """Report only battery values actually supplied by the operating system."""
    report = _system_profiler_buttons()
    hid_fields = _hid_battery_fields()
    paired = [
        device
        for device in IOBluetooth.IOBluetoothDevice.pairedDevices()
        if str(device.nameOrAddress()).startswith("EchoBtn")
    ]
    if not paired and not report:
        print("No paired Echo Button is visible to macOS.")
        return 1

    for device in paired:
        name = str(device.nameOrAddress())
        details = report.get(name, {})
        reported = {
            key: value
            for key, value in details.items()
            if "battery" in key.lower() or "charge" in key.lower()
        }
        raw = {
            "single": int(device.batteryPercentSingle()),
            "combined": int(device.batteryPercentCombined()),
            "headset": int(device.headsetBattery()),
        }
        print(f"{name}: connected={bool(device.isConnected())}")
        if reported:
            print(f"  macOS battery fields: {reported}")
        else:
            print("  macOS device report: no battery field")
        if hid_fields.get(name):
            print(f"  HID battery fields: {hid_fields[name]}")
        else:
            print("  HID device record: no battery field")
        print(f"  IOBluetooth raw battery properties: {raw}")
        if not reported and not hid_fields.get(name) and all(value == 0 for value in raw.values()):
            print("  result: unknown; zero is not a verified 0% reading")
    return 0


class BleBatteryProbe(Foundation.NSObject):
    """Look for the standard BLE Battery Service on an Echo Button."""

    def centralManagerDidUpdateState_(self, manager):
        if manager.state() != CoreBluetooth.CBManagerStatePoweredOn:
            print(f"CoreBluetooth state: {manager.state()} (waiting for Bluetooth)")
            return
        print("Scanning BLE advertisements for EchoBtn devices...")
        manager.scanForPeripheralsWithServices_options_(None, None)

    def centralManager_didDiscoverPeripheral_advertisementData_RSSI_(
        self, manager, peripheral, advertisement, rssi
    ):
        self.advertisement_count += 1
        name = str(peripheral.name() or advertisement.get("kCBAdvDataLocalName") or "")
        if not name.startswith("EchoBtn") or self.peripheral is not None:
            return
        self.found_button = True
        self.peripheral = peripheral
        print(f"Found {name} over BLE; connecting to check Battery Service...")
        manager.stopScan()
        peripheral.setDelegate_(self)
        manager.connectPeripheral_options_(peripheral, None)

    def centralManager_didConnectPeripheral_(self, manager, peripheral):
        peripheral.discoverServices_([CoreBluetooth.CBUUID.UUIDWithString_("180F")])

    def centralManager_didFailToConnectPeripheral_error_(
        self, manager, peripheral, error
    ):
        print(f"BLE connection failed: {error}")
        self.finished = True

    def peripheral_didDiscoverServices_(self, peripheral, error):
        if error:
            print(f"BLE service discovery failed: {error}")
            self.finished = True
            return
        services = peripheral.services() or []
        battery_services = [
            service
            for service in services
            if str(service.UUID().UUIDString()).lower() == "180f"
        ]
        if not battery_services:
            print("BLE Battery Service (0x180F): absent")
            self.finished = True
            return
        for service in battery_services:
            peripheral.discoverCharacteristics_forService_(
                [CoreBluetooth.CBUUID.UUIDWithString_("2A19")], service
            )

    def peripheral_didDiscoverCharacteristicsForService_error_(
        self, peripheral, service, error
    ):
        if error:
            print(f"BLE characteristic discovery failed: {error}")
            self.finished = True
            return
        characteristics = service.characteristics() or []
        if not characteristics:
            print("BLE Battery Level characteristic (0x2A19): absent")
            self.finished = True
            return
        for characteristic in characteristics:
            peripheral.readValueForCharacteristic_(characteristic)

    def peripheral_didUpdateValueForCharacteristic_error_(
        self, peripheral, characteristic, error
    ):
        if error:
            print(f"BLE battery read failed: {error}")
        else:
            value = bytes(characteristic.value() or b"")
            if len(value) == 1 and value[0] <= 100:
                print(f"BLE Battery Level: {value[0]}%")
            else:
                print(f"BLE Battery Level returned unexpected data: {value.hex()}")
        self.finished = True


def ble_scan(seconds: int) -> int:
    """Scan and, only for an Echo Button, request standard battery data."""
    probe = BleBatteryProbe.alloc().init()
    probe.manager = None
    probe.peripheral = None
    probe.found_button = False
    probe.finished = False
    probe.advertisement_count = 0
    probe.manager = CoreBluetooth.CBCentralManager.alloc().initWithDelegate_queue_options_(
        probe, None, None
    )
    deadline = time.monotonic() + seconds
    try:
        while not probe.finished and time.monotonic() < deadline:
            Foundation.NSRunLoop.currentRunLoop().runMode_beforeDate_(
                Foundation.NSDefaultRunLoopMode,
                Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.1),
            )
    finally:
        probe.manager.stopScan()
        if probe.peripheral is not None:
            probe.manager.cancelPeripheralConnection_(probe.peripheral)
    if not probe.found_button:
        print(
            f"Saw {probe.advertisement_count} BLE advertisements, "
            "but no EchoBtn; battery status remains unknown."
        )
        return 1
    if not probe.finished:
        print("BLE battery check timed out; battery status remains unknown.")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("mac-status", help="query macOS paired-device battery data")
    scan = subcommands.add_parser("ble-scan", help="look for BLE Battery Service")
    scan.add_argument("--seconds", type=int, default=45)
    args = parser.parse_args()
    if args.command == "mac-status":
        return mac_status()
    return ble_scan(args.seconds)


if __name__ == "__main__":
    sys.exit(main())
