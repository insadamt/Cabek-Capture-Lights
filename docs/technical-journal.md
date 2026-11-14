# Technical journal

A concise history of changes and what was verified. Full investigation logs from November 2026 are preserved in the [archive](archive/technical-journal-2026-11.md).

## 13 November 2026 — ESP32 and DMX

The serial and DMX firmware were stabilized using separate ESP32 UARTs. Legacy commands `0`–`4` and `?` were kept. The old corrupted-console issue was not reproduced consistently, so its original cause remains unconfirmed.

## 14 November 2026 — Lighting effects

Custom RGB protocol `rgb8-v1` and global RGB effects were added. The first implementation also included application-readiness states, an API bridge and simulated pixel effects.

## 14 November 2026 — Simpler controller

The lighting API was reduced to two routes: `POST /api/lights/set` and `POST /api/lights/off`. It no longer requires CABEK AI readiness or a scan lifecycle.

The controller now uses one serial-owning worker, supports configurable animations, and retains legacy fixed-color commands. CABEK AI sends automatic lighting commands itself, and its settings page forwards manual tests through the backend.

## Verification

Automated API, effect, serial and firmware build checks were recorded in the original journal and implementation history. These tests used mocks or pseudo-terminals where appropriate.

**Physical verification of the updated API, RGB firmware and LED effects remains pending.** Before deployment, check fixed colors, custom RGB, effects, USB reconnection and the CABEK AI scan sequence on the actual tunnel.

See [Hardware](hardware.md) for the checklist.
