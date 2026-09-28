# Echo Button on macOS: first hardware test

These are historical protocol and feasibility notes. For the current Home Assistant integration and installation steps, see [README.md](../README.md).

This small probe checks whether an Amazon Echo Button can send raw Bluetooth Classic/RFCOMM bytes directly to this Mac. The Python capture reports an experimental battery percentage and press/release events. It does not connect to Alexa or Home Assistant.

## Build

Requires macOS and Apple Command Line Tools:

```sh
DEVELOPER_DIR=/Library/Developer/CommandLineTools make
./build/echo_button_probe status
```

## Try one button

1. Turn on Bluetooth in System Settings. If macOS asks for Bluetooth access for the terminal, allow it.
2. Hold one Echo Button until its light turns orange. This may interrupt its existing Alexa pairing.
3. Pair the button in System Settings > Bluetooth.
4. Run `./build/echo_button_probe status` and note the `EchoBtn...` address.
5. Run `./build/echo_button_probe listen ADDRESS rfc`, replacing `ADDRESS` with the paired address. `rfc` selects the button's advertised `RFC SERVER` service. The default `spp` service connected but produced no data on the tested button.
6. Press and release the button. The probe prints each received buffer in hexadecimal. Stop with Ctrl-C.

The probe discovers the RFCOMM channel from the button's SDP records; it does not assume a channel number. Each `RX` line is a socket buffer, not necessarily one complete Echo Button packet. Keep the first capture for protocol research; it may contain a device identifier.

## Observed on this Mac

The tested button advertised `RFC SERVER` with service class `0x1201` on channel 4 and a separate Serial Port Profile service (`0x1101`) on channel 2. Channel 4 produced initialization buffers of 54 and 32 bytes followed by 40-byte button records. In the observed 40-byte records, byte 29 was `0x02` on press and `0x03` on release; byte 39 was `0xF1`. The pasted spec's `0xC0`/`0xC1` assumption for byte 39 did not match this button. The raw local capture is in `captures/`, which is excluded from Git because it includes the button identifier.

On this Mac, the command sandbox reports Bluetooth as off even while System Settings shows it on. A direct device-access check confirmed that the controller is on. The live commands need direct device access; a sandboxed `status` or `scan` result is misleading.

The experimental `scan` command returned inquiry error `0x00000001` on this Mac, although System Settings discovered and paired the button. Use System Settings for discovery and pairing.

## Python battery-status probe on the Mac

Set up the Python bindings and run the probe:

```sh
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements-mac.txt
./.venv/bin/python mac/battery_probe.py mac-status
./.venv/bin/python mac/battery_probe.py ble-scan --seconds 60
```

`mac-status` checks the paired-device report, HID registry, and IOBluetooth battery properties. The tested Echo Button had no reported battery field in the first two sources. IOBluetooth returned zero for all queried battery properties, but the button still operated, so this is not a verified 0% reading. The result is **unknown**.

The Python BLE scan saw nearby devices but no `EchoBtn` advertisement, including while this button was pressed and while it was in orange pairing mode. Thus we have not found a standard BLE Battery Service to read on this button. The RFCOMM 40-byte press records also showed no battery field.

The Python RFCOMM capture and comparison commands are:

```sh
./.venv/bin/python mac/rfcomm_capture.py --seconds 30 --output captures/before.hex
./.venv/bin/python mac/rfcomm_capture.py --seconds 30 --output captures/after.hex
./.venv/bin/python mac/compare_captures.py captures/before.hex captures/after.hex
```

Press and release the same button during each capture. The Python RFCOMM capture receives a 54-byte initialization message, a 32-byte status message, and 40-byte press/release records. Byte 27 of the 32-byte message tracked a controlled AAA battery swap: the original pair reported 64% and then 61%; the fresh pair reported 100% on two connections; reinserting the original pair reported 62%; and restoring the fresh pair reported 100% again. Bytes 29–30 are a big-endian 16-bit checksum, not a second battery field. Its high byte changed from 3 to 4 when the sum crossed 1024. [Amazon's Classic Bluetooth gadget code](https://github.com/alexa-samples/Alexa-Gadgets-Embedded-Sample-Code/blob/master/ConnectionHelpers/BT/Checksum/checksum.c) calculates this checksum from the command, error byte, and payload, excluding the sequence byte. That formula matched all 37 saved frames. The return to 62% with the original pair rules out a simple reset-to-100 effect from power cycling.

The Python RFCOMM capture prints byte 27 as an **experimental battery percentage** when the 32-byte status message has the observed format. It appears at connection startup, so a reading requires connecting to the button. The field has been checked on one Echo Button and three battery pairs; its accuracy and behavior across other buttons or battery types remain unverified. Raw captures in `captures/` contain the button identifier and are excluded from Git.

A third AAA pair reported 63% at byte 27. The checksum was `0x03EB`, as predicted by the same formula.

The same Python capture reports `Echo Button pressed` and `Echo Button released` when it receives the observed 40-byte event frames. This was checked against 17 saved event records and one live press/release. Its stream parser buffers incomplete frames, separates combined ones, unescapes reserved bytes, and checks the packet checksum. Boundary tests and replay of all saved captures passed. This covers the frame formats observed so far, though other button firmware could send additional formats.

## Button light research (paused)

The Echo Button has RGB LEDs, and Amazon's [GadgetController.SetLight skill directive](https://developer.amazon.com/en-US/blogs/alexa/post/ef044c94-db8e-49da-97a6-da124b0f786b/tips-for-building-echo-button-skills-with-the-gadgets-skill-api-bet) can make Alexa animate them. This confirms the LEDs are remotely controllable through an Echo device. It does not expose the direct Bluetooth command bytes needed by the Mac. The user observed the same blue flash on button press both while connected to the read-only Python capture and while disconnected from the Mac. This confirms that the ordinary blue press flash is generated by the button itself, without a host light command. The public Classic gadget examples document the packet envelope, escaping, and checksum; the local `encode_packet` helper reproduces all 37 saved packet envelopes, but the button-specific light payload is still unknown. At the user's request, direct light control is paused; the working Mac prototype focuses on press/release and experimental battery status.

## Home Assistant OS Pi transport test (historical)

A Home Assistant OS Pi running Core 2026.9.3 passed an early BlueZ transport test. Button A advertised the working `0x1201` RFCOMM service. Home Assistant Core connected to the host system D-Bus with Unix file descriptor passing, registered a client profile, and received an RFCOMM socket. Two physical presses produced four 40-byte records with state bytes `02, 03, 02, 03`, matching the Mac press/release observations. The startup buffer's experimental battery field was `0x3d` (61%).

That one-connection probe has been replaced by the integration in `custom_components/echo_button/`. Use the installation and pairing instructions in [README.md](../README.md); no YAML configuration is needed.
