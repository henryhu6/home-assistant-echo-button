# Release readiness

Status: hardware preview. Do not publish this as a reliable button automation integration yet.

## Verified on the current Pi

- [x] UI flow can discover and add two paired Echo Buttons on Home Assistant OS with Core 2026.9.3.
- [x] Both devices show Action, Connection, and experimental Battery entities.
- [x] Connected presses have produced ordered Press start and Press end events.
- [x] Stream parser, socket ownership, and pairing error regression tests pass locally.
- [x] Home Assistant configuration check passes after the installed changes.

## Release blockers

- [ ] Establish reliable first-press behavior after idle disconnection. The Pi sometimes receives no event frame or only Press start on wake. Do not infer a press or release from Connection changes.
- [ ] Reproduce and explain the intermittent extra Press start reported on Button A.
- [ ] Investigate the prolonged BlueZ `br-connection-already-connected` error and recovery behavior.
- [ ] Retest pairing an unpaired button, including the late-bond error path.
- [ ] Add Home Assistant config-flow and config-entry lifecycle tests; the current unit suite exercises protocol and D-Bus helper behavior without Home Assistant Core.
- [ ] Verify a real Home Assistant automation fires once per physical press, including after idle and a Core restart.
- [ ] Exercise config-entry removal and re-addition, and cold restart with both buttons configured.
- [ ] Validate the battery field against a controlled swap on the second button, or remove the percentage claim from the public UI.
- [ ] Install from a clean repository on another Home Assistant OS host and document adapter and permission requirements.
- [ ] Test BlueZ service restart and recovery of the registered RFCOMM profile.

## Publication setup

- [x] Keep all runtime files under `custom_components/echo_button/`, add a root `hacs.json`, and prepare CI checks.
- [ ] Create a public GitHub repository and choose a maintainer account.
- [ ] Add real `documentation`, `issue_tracker`, and `codeowners` values to `manifest.json` before HACS publication.
- [ ] Add a license, repository description, and topics; run the HACS repository validator.
- [ ] Tag and publish a release only after the release blockers are resolved.

HACS requires a public GitHub repository, manifest URLs and code owner, and brand assets. The local folder has no GitHub repository yet, so those fields cannot be filled with valid values. See the [HACS integration requirements](https://www.hacs.xyz/docs/publish/integration/) and [Home Assistant custom integration localization guidance](https://developers.home-assistant.io/docs/internationalization/custom_integration/).
