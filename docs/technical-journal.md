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

## 14 Nov 2026 — Minimal direct lighting controller

- Replaced lifecycle/preview APIs with exactly `POST /api/lights/set` and `/off`.
  Removed readiness gates, capture ownership, simulation/pixel drivers and their
  state machines. Firmware and DMX transmission code remain unchanged.
- Reused global interpolation and named choreography; added color_cycle, palettes,
  uniform speed/duration semantics, easing and indefinite repetition. Finite
  effects hold their final RGB. One worker owns serial updates and prioritizes OFF.
- Basic legacy colors require no handshake. RGB is checked only when needed;
  matching acknowledgments establish initial delivery. USB errors return 503;
  unsupported RGB returns 501. Later frame errors log and reconnect automatically.
- Updated CABEK AI to send direct commands with one HTTP worker and its own
  ten-second completion timer; removed its lighting readiness probe. Updated the
  frontend maintenance panel and loopback-only proxy to the new contract.
- Software verification: 86 lighting tests (mocked serial/API/effect/worker and
  real pyserial pseudo-TTY recovery), 20 CABEK AI lighting/capture tests, seven
  frontend lighting/proxy tests and production build, native firmware parser checks,
  and all three PlatformIO firmware builds passed. These do not establish physical USB, DMX or LED behavior.
  Follow the [manual hardware checklist](lighting-effects.md) for acceptance.

The earlier lifecycle/preview and simulation descriptions above are historical;
the current contract is the [minimal API reference](lighting-api.md).

## 14 Nov 2026 — Backend-only application lighting

- Removed the frontend lighting maintenance page, HTTP client, public service URL
  and Vite lighting proxy. CABEK AI already owns startup, capture, completion timing
  and shutdown commands; no browser lighting endpoints were added to CABEK AI.
- The independent service retains its two local diagnostic endpoints. Hardware
  firmware and the backend effect sequence are unchanged.
- Verification: 20 backend lighting/capture tests, 42 frontend routing/capture
  tests and the production build passed. Physical lights were not tested.

## 14 Nov 2026 — Central settings and backend-mediated light tests

- Added `/settings`, opened by five rapid Dynamic Island clicks, with manual light
  tests. Single-click home navigation is deferred 600 ms to distinguish the gesture.
- Added two local CABEK AI settings actions that forward to the lighting service,
  preserving errors and keeping its address out of browser configuration. Accepted manual
  tests cancel the earlier completion timer and share serialized backend delivery
  with automatic lighting, so stale retries cannot replace a test.
- The independent lighting service and firmware are unchanged. Both backend and
  Vite enforce local settings access; the hidden gesture is only navigation.
- Verification: 34 frontend gesture/settings/island/routing tests, 35 backend
  settings/lighting/capture tests and the production build passed. No browser
  automation or physical hardware tests were performed. Failed manual tests
  preserve the previous automatic sequence; newer capture events remain pending.
