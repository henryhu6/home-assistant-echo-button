# Echo Button project

## Completed: macOS hardware probe

- [x] Check macOS Bluetooth controller and toolchain.
- [x] Build a Classic Bluetooth scanner and RFCOMM packet logger.
- [x] Confirm Bluetooth is on outside the command sandbox.
- [x] Put one Echo Button in pairing mode and pair it with macOS.
- [x] Discover its advertised RFCOMM service and capture real press/release bytes.
- [x] Confirm the observed 40-byte event records and state values from hardware.
- [x] Report battery percentage and press/release together in the Python Mac capture; verify against saved frames and a live press.
- [x] Buffer RFCOMM bytes into observed 54-, 32-, and 40-byte frames; test split and combined reads and replay saved captures.

## Home Assistant OS feasibility on the Pi

- [x] Prepare a one-connection BlueZ Profile1 probe for Home Assistant Core.
- [x] Get access to the Home Assistant OS Pi and confirm Core can reach host D-Bus and pass a socket FD.
- [x] Pair one button with the Pi and inspect its discovered service UUIDs; the working Mac service was class `0x1201`, while the silent SPP service was `0x1101`.
- [x] Receive raw press/release buffers in Home Assistant Core and compare with the Mac capture: two physical presses produced `02, 03, 02, 03` in four 40-byte records.

## Battery-status research on macOS

- [x] Check the Mac's paired-device Bluetooth report and IOBluetooth battery properties.
- [x] Check the Mac's HID registry for a battery field.
- [x] Check whether the button exposes the standard BLE Battery Service using Python while pressed and in pairing mode; it did not advertise to the scanner.
- [x] Compare fields that vary across the existing RFCOMM button-event frames; only sequence, state, and one trailing byte varied.
- [x] Capture RFCOMM messages from the Mac directly in Python with PyObjC.
- [x] Compare the 32-byte startup message's byte 27 before and after a fresh AAA battery swap: 61 to 100; a repeat connection also read 100.
- [x] Display the apparent battery percentage in the Python RFCOMM capture with an experimental label.
- [x] Reinsert the old battery pair to distinguish battery response from a power-cycle reset: it read 62%, then the fresh pair read 100% again.
- [x] Identify bytes 29–30 as the packet's 16-bit checksum using Amazon's Classic Bluetooth sample; verify all 37 captured frames.
- [x] Read the field on the second Echo Button; it reported 39% at first connection and 59% after a restart.
- [ ] Validate the second button's apparent battery percentage against a controlled battery swap; the 20-point change across connections makes its accuracy uncertain.

## Button light research on macOS (paused at user request)

- [x] Confirm remote RGB animation exists through Amazon's GadgetController.SetLight directive.
- [x] Identify the Classic Bluetooth packet envelope and checksum; verify all saved frames and implement an encoder.
- [x] Observe the ordinary blue press flash while connected to the read-only Mac capture.
- [x] Compare the press flash with the button disconnected; it still flashes blue, confirming built-in feedback.

Light control is outside the current project scope. The direct Bluetooth payload is unknown; no Mac light command has been sent.

## Native Home Assistant integration

- [x] Replace the YAML probe with a UI config flow that scans for Classic Bluetooth Echo Buttons, pairs through BlueZ, and allows another button to be added later.
- [x] Register a Home Assistant device with a press/release event entity and an experimental battery sensor.
- [x] Implement a shared RFCOMM profile with per-button sessions and connection retries.
- [x] Install on the Pi and confirm that the setup flow discovers an already paired button and creates a device with two entities.
- [x] Confirm Home Assistant's automation editor offers Event received with Press start and Press end for the new device.
- [x] Confirm a live physical press updates the event entity and that the experimental startup battery value appears on the device page.
- [x] Confirm a full press/release cycle yields both Press start and Press end after the RFCOMM connection is established.
- [x] Pair the second button from the setup flow; Home Assistant now shows Button B and Button A as two devices, each with Action, Connection, and Battery entities, and a live Button B press produced Press start and Press end.
- [x] Verify Button A still emits both events after Button B was added.
- [ ] Retest a fresh pairing with the BlueZ late-bond recovery installed; the first Button B attempt returned AuthenticationFailed while BlueZ completed the bond, and overlapping setup calls then created the entry.
- [x] Test a forced BlueZ disconnect and verify that the first button reconnects and again emits Press start and Press end.
- [x] Confirm Home Assistant Core restarts with the config entry and both entities still present.
- [x] Filter duplicate press states and release states with no preceding press within each RFCOMM connection; replay saved captures and pass seven parser/transition tests.
- [x] Re-arm after two seconds without a press frame so an old unmatched press cannot suppress the next physical press; eight local tests pass.
- [x] Confirm a live press produces Press start and Press end after deploying the transition filter and restarting Core.
- [ ] Investigate the intermittent extra Press start: after one quick physical press, the event entity still displayed Press start as its latest event after Press end appeared in activity. A later single press produced one ordered start/end pair (frame sequences 8 and 9), and the latest state was Press end. Debug logs now record only decoded state, packet sequence, and emission status for the next occurrence.
- [ ] Determine whether a reliable first press is possible after the button has disconnected or slept. In a controlled Button A disconnect, one physical press reconnected RFCOMM but delivered no button frame; Home Assistant activity showed the old Press end on reconnection. Amazon says Echo Buttons sleep after ten minutes of inactivity.
- [x] Investigate why a wake press can show Press start without Press end. Button B connected after a confirmed quick press. The Pi received 54- and 32-byte startup frames and one valid 40-byte Press start frame, but no release bytes. A second quick press on the established connection delivered both 40-byte Press start and Press end frames. The parser emitted each frame it received. The release is absent at the RFCOMM socket on wake; an HCI capture would be needed to determine whether the button never transmitted it or transmitted before the profile was ready. Connected is the live RFCOMM socket status, not a replacement for release events.
- [x] Remove the temporary INFO level raw RFCOMM trace from `bluez.py` on both the Pi and local workspace. Home Assistant Core configuration check passed and Core was restarted. Earlier raw bytes remain in historical private Core logs.
- [ ] Investigate Button A's prolonged BlueZ `br-connection-already-connected` error while `bluetoothctl info` reported `Connected: no`. A BlueZ disconnect request did not clear it. The button eventually reconnected after earlier attempts failed; determine why recovery took so long.
- [x] Confirm on the Pi that the Connection diagnostic changes on disconnect/reconnect without replaying the old event in Activity. Both buttons reconnected on a press, and Activity initially showed an old Press end immediately before the real Press start; integration logs contained only Press start. After the fix, a controlled Button B disconnect and reconnect produced only Connection diagnostic changes, with no replayed button event.
- [ ] Verify an actual Home Assistant automation fires once per physical press and does not fire on a restored event during reconnection.
- [ ] Test config-entry removal and a press after a cold restart on the Pi.
- [x] Confirm the config-flow instructions render after adding `translations/en.json` and refreshing the Home Assistant frontend.
- [x] Add local Home Assistant brand icons (`icon.png` and `icon@2x.png`) and verify the placeholder is replaced on both Echo Button device pages after a Core restart.
- [x] Rename Activity entity labels to Action and Connection on both button pages, preserving the existing entity unique IDs.
- [x] Reproduce and fix the socket ownership race where an old reader could close a replacement RFCOMM socket; add a regression test.
- [x] Move per-button runtime sessions from a shared `hass.data` lookup to config entry `runtime_data` and verify both existing devices still load after a Core restart.
- [x] Run parser tests against the integration protocol module rather than the older Mac copy, and add Ruff to catch undefined names.
- [x] Add local HACS metadata and a release readiness checklist without placeholder repository URLs.
- [x] Prepare a GitHub Actions workflow for parser, transport, and Ruff checks once the repository exists.
- [x] Turn host D-Bus connection and call failures into setup-flow errors; cover the previously observed late-bond pairing path with a unit test.
- [ ] Prepare a public HACS repository with a real documentation URL, issue tracker, code owner, and release tag; validate a clean install on another Home Assistant OS host.

## Known issue

- The command sandbox hides the Mac's Bluetooth controller state. Bluetooth checks and live scans must run with direct device access.
- The button's SPP service connects but emits no data. Its RFC SERVER service did emit button records.
- The probe's `scan` command returned inquiry error `0x00000001` on this Mac. System Settings discovery and pairing worked.
