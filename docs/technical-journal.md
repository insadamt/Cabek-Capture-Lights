# Technical journal

A short record of what changed and what was actually verified. Detailed investigation notes and test output are preserved in the [archive](archive/technical-journal-2026-11.md).

## 13 Nov 2026 — Stable ESP32 serial and DMX

- Rebuilt the ESP32 firmware around separate USB Serial (UART0) and DMX output (UART2), without the incompatible external DMX library.
- Kept existing GPIO wiring and legacy color commands `0`–`4`, plus `?` for status.
- Tested serial communication and continuous DMX transmission on the ESP32. The reported historical garbage output could not be reproduced reliably, so its root cause remains **unconfirmed**.

## 14 Nov 2026 — Effects and local API

- Added custom RGB firmware protocol `rgb8-v1`, smooth global RGB effects, a driver capability check and a simulation-only pixel engine.
- Moved the lighting REST API and serial ownership into **this repository**. CABEK AI now sends lifecycle events over HTTP instead of managing the USB port.
- Added a protected maintenance preview page to the CABEK AI frontend.

### Verification

Software builds and automated tests passed for the lighting implementation and its separate application integration; an unrelated, intermittent application capture test was recorded in the original journal. The effects migration and standalone-service relocation **were not physically tested** against the new firmware/decoder during implementation.

### Still to check on hardware

- Flash and verify `rgb8-v1` on the real ESP32 after backing up the working firmware.
- Observe all global effects, including startup, capture completion and error states.
- Test USB reconnect, extended operation and physical DMX behavior.
- Verify the NAVIGATE Magic RGB strip's controller and wiring before enabling any physical progressive effects.

For instructions, see [deployment](lighting-deployment.md), [API](lighting-api.md) and [effects](lighting-effects.md).
