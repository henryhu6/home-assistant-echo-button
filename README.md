# Echo Button for Home Assistant

A native Home Assistant custom integration for Amazon Echo Buttons over Bluetooth Classic. Each paired button appears as a device with an event entity for press and release, a connection diagnostic, and an experimental battery sensor. The setup flow scans and pairs buttons in Home Assistant; no separate Home Assistant App or YAML configuration is needed.

## Current status

**Hardware preview, not a public release.** The integration has been installed on one Home Assistant OS Raspberry Pi running Core 2026.9.3. Its setup flow has added two Echo Buttons as separate devices. Live presses on both buttons produced Press start and Press end while connected. After an idle disconnect, a confirmed Button B press reconnected and delivered only a Press start packet to the Pi; the next press on the established connection delivered both events. In another wake test, the Pi received no press packet. An intermittent extra Press start and a prolonged BlueZ connection error also need investigation. The first pairing attempt for the second button returned an error even as BlueZ completed the bond; recovery for that timing race needs a fresh-pair test. Clean installation on another host remains untested. The [release checklist](docs/release-readiness.md) tracks these blockers.

Light control is outside the current scope. Battery percentage comes from one reverse engineered startup field; a controlled battery swap supported the interpretation on one button. The second button reported 39% and then 59% across connections, so accuracy across buttons is not established.

## Install for testing

1. Use a Home Assistant OS host with a working local Bluetooth adapter. The integration needs Home Assistant Core access to the host BlueZ system D-Bus and Unix file descriptor passing. Other installation types are untested.
2. Copy `custom_components/echo_button/` from this repository to `/config/custom_components/echo_button/` on the Home Assistant host.
3. Restart Home Assistant.
4. Open **Settings → Devices & services → Add integration → Echo Button**.
5. Hold a button until its light turns orange, select **Submit** to scan, choose the button, and finish setup. A previously paired button can also be selected. Pairing with Home Assistant may replace its Alexa or Mac pairing.

The device page should show an **Action** event entity, a **Connection** diagnostic binary sensor, and a **Battery** diagnostic sensor. In an automation, choose **Event received** for that device and select **Press start**. **Press end** is also available. Action retains only the last real button event across Bluetooth disconnects; Connection shows the live RFCOMM link state. The battery value is read when the connection starts, so it can be unknown until the button connects.

The integration includes a local round-button icon in `brand/`. Home Assistant 2026.3 or newer shows it on the integration and device pages after a Core restart. Each paired button uses the same integration icon; its device name identifies the individual button. The editable SVG source is `assets/echo_button_icon.svg`.

[Amazon says Echo Buttons sleep after ten minutes of inactivity](https://developer.amazon.com/en-US/blogs/alexa/post/ef044c94-db8e-49da-97a6-da124b0f786b/tips-for-building-echo-button-skills-with-the-gadgets-skill-api-bet). In one observed wake connection, the Pi received Press start but no Press end packet; in another, a reconnecting press delivered no event packet. The first press after disconnection is therefore not yet reliable as an automation trigger, and Press end should not be used for a critical automation. This is a current release blocker.

## How it works

The setup flow talks to BlueZ through system D-Bus to scan Classic Bluetooth devices and pair the selected button. A shared BlueZ client profile opens the button's RFCOMM service `0x1201`. The stream parser validates packet framing and checksum before decoding press/release records and the experimental battery field. A per-connection transition filter ignores rapid repeated press states and releases without a preceding press, and re-arms after a gap if a release was lost. One profile manager supports multiple configured button sessions; connections retry after failures or disconnections.

The physical protocol findings and Mac test commands are in [research notes](docs/research.md). Raw capture files can contain a device identifier and are intentionally excluded from source control.

## Development checks

Install the test dependencies with `python3 -m pip install -r requirements-test.txt`, then run `python3 -m unittest discover -s tests` and `ruff check custom_components/echo_button tests`. These checks exercise the integration's parser, a reconnection race in its transport, and undefined names. The Home Assistant setup flow, entity lifecycle, and transport must also be checked on hardware; local checks alone do not establish working pairing or automations.

To remove the integration, delete each Echo Button entry in **Settings → Devices & services → Echo Button**, remove `/config/custom_components/echo_button/`, and restart Home Assistant. This does not remove the Bluetooth bond from BlueZ; remove the paired device separately if you want to pair it with another host.

Planned work is tracked in [TODO.md](TODO.md).
