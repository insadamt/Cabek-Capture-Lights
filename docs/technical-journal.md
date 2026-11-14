# CABEK ESP32 technical journal

This file records the DMX/serial investigation, implementation decisions, observed
results, and manual acceptance checks. It serves as the technical report and journal
entry in one place. It depends on the firmware, PlatformIO environments, serial test
script, and locally retained evidence described below.

## 2026-11-13 — Terminal-controlled DMX and UART isolation

### Finding and limits

The reported historical serial corruption has **not been reproduced** in this
session. Do not attribute it to UART0, the transceiver, a library, or the USB bridge
without a failing capture. The original board produced 462 readable bytes at
115200 baud, including ROM boot text, the application menu, and `READY`.

Two source/build problems were established:

- `src/main.cpp` contained only a partial `loop()`. A baseline PlatformIO build
  failed because `Serial`, `handleCommand`, and `delay` were undeclared; `setup()`
  was also absent. This source could not have produced the firmware on the board.
- The installed Arduino core is 3.3.12 (ESP-IDF 5.5.5), with Espressif32 platform 8.0.0. Its local
  `soc/uart_periph.h` defines `uart_signal_conn_t` with pins and IRQ but no `module`.
  That explains the previously reported `esp_dmx` compilation failure. It does
  **not** establish the cause of the earlier runtime corruption or LoadStoreError.
  The same incompatibility is recorded in the library's
  [upstream issue](https://github.com/someweisguy/esp_dmx/issues/181).

There was no Git repository, `docs/` directory, or project instruction file when
the investigation started. No last-known-working automatic source, modified DMX
fork, or crash backtrace was present. Git was initialized for the requested single
consolidated commit. The original source/configuration and existing build images
were preserved under ignored `.rollback/` before editing or rebuilding.

### UART, clock, and transport evidence

- USB device: `/dev/ttyUSB0`, CP2102 bridge, VID:PID `10C4:EA60`, USB location `3-2`.
- Esptool identified an ESP32-D0WD-V3 revision 3.1, 4 MB flash, 40 MHz crystal.
  The installed board configuration selects 240 MHz CPU and DIO flash.
- The saved original ELF's `setup()` initializes `Serial0` at 115200 and `Serial2`
  at 250000, 8N2, RX16/TX17. Its `loop()` passes UART number 2 and 513 bytes to
  `uart_write_bytes_with_break`, with a 30-bit (120 microsecond) trailing break.
  This contradicts the proposed UART0 misrouting for that saved build.
- The full-flash backup matched the saved original application at offset `0x10000`
  byte-for-byte, so the disassembly describes the actual original application.
  A second reset/command capture contained 3887 ASCII bytes, successful responses
  to `12340`, and repeated menu-tail/`READY` fragments before the ROM boot banner.
  These pre-boot reset artifacts are retained as an unexplained anomaly; they are
  distinct from the reported continuous non-ASCII stream during DMX operation.
- A trailing break is the documented behavior of
  [`uart_write_bytes_with_break`](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/uart.html).
  It can delimit the next frame when followed by a sufficient mark. Its use in
  the previous binary alone is not evidence of a serial-corruption bug.
- The initial full-flash read at 115200 was interrupted before completion. A
  subsequent read at 460800 failed after approximately 172 KB with `Packet content
  transfer stopped`. This establishes a failed faster transfer, not its physical
  cause. Upload speed is kept at 115200. The conservative retry completed all
  4194304 bytes before uploads (377 seconds). Backup SHA-256:
  `f95642560411c3c078703816b8422dc46c3783d383394519f378638db4abefc7`.
- User-confirmed setup: MAX485 connected to ESP32; DMX decoder disconnected.
  No wiring or power connections were changed.
- Host kernel logs show the current CP2102 attachment at 16:31:52 and no USB
  disconnect during the failed faster backup. Earlier disconnects predate this
  investigation and cannot be distinguished from deliberate unplugging.
  ModemManager and brltty were inactive; neither was changed.

The observed ROM and application text was readable, so that capture does not
implicate the ROM bootloader or demonstrate a USB bridge/host-monitor defect.
The unusual crystal measurement and earlier crash remain historical observations
without a reproducible failure or address trace to decode.

### Implementation and important decisions

`src/main.cpp` owns USB UART0 explicitly on TX1/RX3 at 115200, 8N1. Commands select
RGB channels 1–3 at address 001: `1` red, `2` blue, `3` green, `4` white, `0` off.
CR/LF, spaces, and tabs are ignored. Invalid input leaves the selected color
unchanged. Startup selects off; the last selection remains in the static universe
until another command or reset. Input processing is bounded per loop to keep
refresh running during pasted commands.

The first serial-only test measured UART0 at 115942 baud with Arduino's automatic
1 MHz REF_TICK source. The local HAL chooses REF_TICK for rates up to 250000 and
uses a fractional divider; that explains the reported baud value. The stream was
readable and DMX was not initialized, so this is not evidence of DMX changing
UART0's baud. UART0 now explicitly selects APB before `begin()` for a closer
divider. The tester accepts hardware readback within 0.01% of 115200 (including
115201), rather than requiring mathematically exact equality. The original failed
test and raw capture are retained in `.evidence/serial_only-before-clock-fix*`.

`src/dmx_output.cpp` exclusively owns UART2 through public ESP-IDF functions;
there is no parallel `Serial2.begin()` or third-party DMX driver. Configuration is
250000 baud, 8N2, APB clock, TX17, no flow control. DE remains GPIO25 and active-low
RE remains GPIO26. The receiver is disabled for this transmit-only application.
DE stays low in initialization-only mode and after a detected output failure.

Every transmitted frame has a leading break requested for 120 microseconds, a
mark-after-break requested for 16 microseconds, then the null start code and all
512 slots. Only slots 1–3 change. UART TX inversion generates the break while the
pin remains attached to UART2, avoiding GPIO ownership changes. The sender drains
the frame before changing polarity again. Actual timing still requires a scope
or logic-analyzer capture; scheduler/API overhead can lengthen requested delays.

All UART configuration/write/drain results are checked. Failures disable the
transceiver and print a fault once instead of repeatedly resetting or flooding
the console. The static 513-byte buffer is not allocated on a task stack or
modified concurrently. The loop yields between frames for the scheduler.

The `?` command reports firmware version, application-image MD5, mode, selected
RGB values, completed frames, errors, heap, uptime, baud rates, crystal frequency,
and reset reason. Logging is limited to startup and responses to input.

`platformio.ini` pins the installed platform to 8.0.0 and defines three builds:

| Environment | Behavior |
| --- | --- |
| `serial_only` | UART0 console, DMX driver not initialized, DE low |
| `dmx_init` | UART2 initialized, no frames sent, DE low |
| `esp32dev` (default) | Continuous UART2 DMX frames |

No library dependency was added. `.gitignore` excludes hidden AI/tool folders,
build products, raw diagnostic evidence, flash backups, and Python caches.

### Validation procedure and results

The final source built successfully for all three environments, with compiler
warnings corrected. The serial tester's negative checks accepted an ordinary
response and rejected corrupt bytes, a Guru Meditation line, a reboot line, and
a DMX fault line.

All three firmware images were uploaded successfully with write-hash verification
at 115200 baud. The board's reported image MD5 matched the built binary for each
tested stage. Results on the actual ESP32, with MAX485 connected and the decoder
disconnected:

| Stage | Commands | Idle hold | Frames during hold | Free heap | Result |
| --- | ---: | ---: | --- | ---: | --- |
| Serial only | 131 | 15 s | 0 | 330720 bytes, stable | PASS |
| DMX initialized | 131 | 15 s | 0 | 328808 bytes, stable | PASS |
| Continuous DMX | 131 | 60 s | 39.58 completed frames/s | 328808 bytes, stable | PASS |

All stages retained readable post-startup serial output, correct command/RGB
state, zero DMX errors, and monotonic uptime. No Guru Meditation, watchdog/panic,
or unexpected reboot was observed during these tests. Minimum free heap remained
298984 bytes. UART0 readback was 115201 baud; initialized UART2 readback was
250000 baud. The production image MD5 was
`6766a59f9c84a96a4210baac53686285`. Its final checked status was command `0`,
RGB `0,0,0`, 2411 completed frames, zero errors, uptime 61630 ms. Production
firmware is left installed and continuously transmitting off.

These bounded tests demonstrate the current console/DMX coexistence; they do not
prove the cause of the historical corruption or rule out longer-term failures.
Physical LED colors and RS485 timing remain unverified with the decoder
disconnected. No memory-error detector or logic analyzer was attached; heap and
crash-log checks are the memory evidence available here.

To repeat the tests, close other serial monitors first. Each script invocation
resets the board, requires the expected firmware MD5 and mode, tests every color,
invalid input, 25 repeated commands, 100 rapid commands, idle hold, frame progress,
uptime, and heap stability, and finishes with off. Any non-ASCII serial bytes,
reboot, panic/fault, missing acknowledgment, wrong RGB, or stalled refresh fails.
Use a Python environment with pyserial; PlatformIO already depends on it.

```sh
pio run -e serial_only -e dmx_init -e esp32dev
pio run -e serial_only -t upload
python scripts/test_serial.py --mode serial_only --firmware .pio/build/serial_only/firmware.bin --log .evidence/serial_only.bin
pio run -e dmx_init -t upload
python scripts/test_serial.py --mode dmx_init --firmware .pio/build/dmx_init/firmware.bin --log .evidence/dmx_init.bin
pio run -e esp32dev -t upload
python scripts/test_serial.py --mode dmx_tx --firmware .pio/build/esp32dev/firmware.bin --log .evidence/dmx_tx.bin --soak-seconds 60
pio device monitor -e esp32dev
```

Local evidence is intentionally ignored: `.evidence/build.log`, raw serial
captures, backup logs, and `.evidence/original-disassembly.txt`. Original build
files and source are in `.rollback/original-build/` and `.rollback/` respectively.
These local backups must be copied separately if the project is moved.
Per-stage results are in `.evidence/serial_only-result.json`,
`.evidence/dmx_init-result.json`, and `.evidence/dmx_tx-result.json`.

The original application can be restored at `0x10000` using
`.rollback/original-build/firmware.bin` with the original boot/partition layout;
the complete starting flash is `.rollback/flash-before.bin`. No rollback was
performed after successful validation. No whole-flash erase was used.

### Manual acceptance checklist

- [ ] With the established wiring and decoder powered normally, select address
  001 and the decoder's RGB/three-channel mode.
- [ ] At 115200 baud, verify readable startup text, `mode=dmx_tx`, and status
  baud rates near 115200 and exactly 250000; repeated `?` queries show increasing
  frames and zero errors.
- [ ] Send `1`, `2`, `3`, `4`, `0`: observe red, blue, green, white, off.
- [ ] Select a color and leave the terminal idle for at least one minute; confirm
  that the light holds without flicker or periodic blackout.
- [ ] Repeat commands and paste `0123401234`; confirm the last command wins and
  the console stays readable. CR/LF must not change the selected color.
- [ ] Reset the board and verify startup off and continued DMX refresh.
- [ ] Measure GPIO17/RS485 output: 250000 baud, 8N2, break at least 120 microseconds,
  MAB at least 16 microseconds, start code zero, 513 slots, correct channels 1–3,
  and continuous frames. Verify UART0 carries only the 115200-baud console.
- [ ] Run a longer serial soak with the decoder connected; no corruption,
  unintended resets, DMX errors, or sustained heap decline.

## 2026-11-13 — Backend-owned application lighting integration

This entry records the significant application integration, its verification and
remaining hardware acceptance. It depends on the unchanged firmware above and the
sibling FastAPI backend and React capture workflow.

### Decision and delivered behavior

Repository inspection found FastAPI rather than Laravel, one local scan manager,
and a backend-owned mock photo capture service. Lighting therefore lives inside
the existing API process, with one serial worker and a separate readiness worker.
The launcher starts BOOTING before application imports; lifespan enters
INITIALIZING and enables readiness checks only after scan/capture recovery finishes.
Actual model availability, the scan supervisor, writable storage and valid provider
photo plans gate READY. Existing pricing readiness remains separate from capture.

Capture delivery owns SCANNING, and validated photo completion owns COMPLETED with
a monotonic 10-second deadline. Failures/interruption never enter success green.
New capture identities supersede previous timers/tests; repeated and stale events
are idempotent. React continues to use its existing capture request; refresh and
navigation never send hardware startup commands.

A persistent exclusive pyserial transport validates the existing OK/STATUS
protocol, queries health, suppresses redundant color writes, detects resets/DMX
stalls, and reconnects with backoff and latest-state replay. Hardware failure
clears current acknowledgment while preserving desired application state. Status
explicitly distinguishes those values and retains historical firmware/last-command
information. One timed maintenance test can run only while healthy/idle and is
superseded by capture. Lighting routes require bearer access; testing requires a
separate maintenance credential. No serial credentials are shipped to React.

Firmware source, GPIO wiring, DMX timing/address/channel mapping and RGB white
remain unchanged. BOOTING uses the existing BLUE/OFF commands in the bridge.
No firmware was uploaded or device reset by this implementation.

### Changed files and commits

Backend commit `c29b3f4` — `feat(lighting): integrate reliable ESP32 control with capture lifecycle`:

- `api/lighting_config.py`, `lighting_protocol.py`, `lighting_state.py`,
  `lighting_service.py`, `lighting_readiness.py`, `lighting_schemas.py` and
  `lighting_routes.py`: configuration, serial ownership, state arbitration,
  readiness, status and authenticated routes.
- `api/__main__.py`, `api/main.py`, `api/config.py`, `api/capture_service.py`:
  launcher/lifespan and actual capture lifecycle integration.
- `.env.example`, `requirements-api.txt`, `README.md`, `docs/lighting-api.md`:
  opt-in configuration, pyserial dependency and operational/API reference.
- `tests/lighting/test_state.py`, `test_bridge.py`, `test_pty.py`,
  `tests/api/test_lighting.py`, `tests/api/test_dossiers.py`: lifecycle, transport,
  security, restart and OpenAPI coverage.

Frontend commit `f440f33` — `docs(capture): describe backend-owned physical tunnel lighting`:
`docs/api-integration.md` explains why the existing React capture flow needs no
new lighting state or browser secret.

This ESP32 repository adds `README.md`, `deploy/cabek-tunnel.service`,
`docs/lighting-deployment.md`, this journal entry and additional hidden AI folder
ignore rules in `.gitignore`. The unit is supplied for operator installation;
it was not enabled on this development machine.

Preexisting changes in all repositories were retained. The backend commit was
prepared and tested separately against its original HEAD so unrelated local
capture/expertise/financial/UI changes are excluded. Existing local stable-port
edits in `platformio.ini` and `scripts/test_serial.py` are also excluded from the
ESP32 integration commit.

### Validation results

- Final backend working tree: **322 tests passed**, including 27 new lighting
  tests; isolated lighting-only commit: **297 tests passed**. One existing
  Starlette/httpx deprecation warning.
- Real pyserial with a Linux pseudo-TTY and emulated firmware: all legacy color
  commands/status, persistent session, missing device and reenumeration replay.
  Mock tests additionally cover corrupt/missing/mismatched acknowledgments,
  ESP32 reboot, stalled DMX frames, reconnect backoff, unavailable hardware,
  blinking, readiness failure/recovery, 10-second expiry, stale events, overlapping
  scans, concurrent HTTP requests, authorization and maintenance expiry/priority.
- Readiness checks cannot delay serial commands; startup recovery cannot falsely
  trigger READY. Tests explicitly block these operations to verify the guarantees.
- React: **663 tests passed across 81 files**; TypeScript/Vite production build
  passed. Existing large-bundle advisory remains.
- PlatformIO: **serial_only, dmx_init and esp32dev all built successfully**;
  no upload. Python compilation and Git whitespace checks passed. New/modified
  implementation files remain below 500 lines. No Playwright/browser automation.
- The sandbox hid USB devices. Host-level enumeration found the ESP32 at its
  stable CP2102 by-id path, but another running serial client owns its exclusive
  lock. An attempted production transport connection correctly refused to steal
  it. That client was left running; new real-device command acknowledgments and
  physical strip behavior remain unverified in this task.
- Systemd unit validation passed using a temporary copy with this host's Python
  executable; the original `/opt/cabek-ai` executable is not installed here.
- Installed pyserial 3.5 in the backend's existing virtual environment. The
  deployment unit still requires actual host paths, service account, serial
  permissions, sample provider configuration and private credentials.

### Manual acceptance and operational limits

Follow the complete [Linux deployment and hardware checklist](lighting-deployment.md)
and the [backend curl procedure](lighting-api.md).
At minimum release the current serial client, observe all five strip outputs,
check startup readiness, complete/fail/interrupt captures, start another capture
during green, test missing/bad/maintenance credentials, unplug/reconnect USB,
reset ESP32 and restart the application/host. Confirm graceful shutdown OFF and
run a sustained hardware soak.

No physical LED colors, real unplug/replug, ESP32 power reset or installed systemd
startup were observed. A host cannot command disconnected hardware: the last LED
output may persist, and forced process termination cannot guarantee OFF without
a firmware host-loss watchdog. The existing firmware was intentionally preserved.
The current camera provider is still simulated; this change adds lighting, not
physical camera drivers. Public access requires authenticated protection for the
whole capture API as well as the new lighting endpoints.

## 2026-11-14 — Advanced effects engine and negotiated RGB output

This combined technical report/journal records the major effects architecture,
compatibility decision and validation. It depends on the FastAPI lifecycle owner,
React maintenance route and backward-compatible firmware RGB extension. API and
operator documentation remains in each relevant repository; sibling repository
instructions prohibit separate reports or journal files there.

### Audit and implementation decisions

The audit found an existing six-state lighting manager, capture hooks, authenticated
routes, exclusive persistent serial transport, readiness worker and reconnect
health validation. Those remain the foundation. Firmware only accepted five fixed
colors, so smooth arbitrary RGB required an advertised extension rather than
pretending the old firmware could animate custom colors. `protocol=rgb8-v1` adds
bounded `R r g b` packets while keeping commands 0–4, `?`, firmware version,
DMX sender, wiring, timing configuration and address/channel mapping compatible.
Timeout/overflow packets drain through newline so payload digits cannot select
legacy colors. No new firmware library, task or dynamically allocated parser
buffer was introduced.

The backend now separates pure global/zone renderers, one-effect arbitration and
a synchronous driver interface inside the existing hardware worker. Monotonic
elapsed time determines output; a default 15 Hz ceiling, I/O-aware scheduling,
quantization and duplicate suppression bound serial traffic. No per-effect workers,
queues or timers are created. Lifecycle revisions invalidate previews, authoritative
capture ownership wins, repeated identical previews do not restart or extend their
cutoff, and the original 10-second completion deadline cancels on new capture.
Shutdown allows a bounded fade before the existing final best-effort OFF.

A–L render on confirmed global RGB hardware. M–P require independent logical zones
and currently run only through `simulated_pixels`. The simulation supports zone
count/mapping, direction, color order and output ceilings without asserting an
unverified physical controller protocol or individual LED addressability. The 24V
NAVIGATE strip remains unverified and no WS2811/pixel hardware driver is enabled.

The existing status/state/test API now also exposes capabilities, effect metadata,
start and stop. Maintenance writes require the separate credential and idle READY;
strict effect-specific schemas reject irrelevant/invalid parameters. Desired frames,
current driver acknowledgment, historical firmware and simulation are distinct.
The opt-in `/maintenance/lights` React panel verifies maintenance permission before
showing controls, retains its token only in memory and performs read-only refreshes.
The whole capture API still needs its existing trusted deployment boundary.

### Verification and investigation

The original backend working-tree baseline passed 322 tests. Expanded lighting
coverage verifies all A–P renderers, easing/interpolation, final frames, brightness,
mock-time expiry, rapid/repeated/concurrent requests, capture priority, lifecycle
completion/new-capture cancellation, warning/shutdown, capability rejection and
simulated mapping. Existing legacy, pseudo-TTY, capture and readiness checks remain.
A reconnect test exposed a frame deadline that could suppress immediate replay;
reconnection now invalidates that deadline. A reconnect handshake terminates a partial RGB packet and discards only recognized
stale RGB responses before firmware status validation. Additional regression checks keep
acknowledgment types valid when switching simulated zone output to global RGB.

Final isolated commit contents: **338 backend tests passed** and **619 frontend
tests passed across 76 files**; the isolated TypeScript/Vite build passed. The
working frontend passed **667 tests across 82 files** and its production build.
The working backend's final run passed **362 tests with one intermittent existing
capture retry failure**; all **68 lighting/API tests** passed. Vite retains its preexisting large-chunk advisory. PlatformIO built
`serial_only`, `dmx_init` and `esp32dev`; the native C++ parser test passed with
`-Wall -Wextra -Werror`. Python compilation and whitespace checks were also run.
No Playwright or browser automation was used.

Working-tree runs intermittently observed an existing capture retry's historical
failed status before its replacement asynchronous analysis started:
`tests/api/test_expertise_capture.py::test_missing_legacy_originals_offer_capture_and_do_not_poison_the_next_scan[True]`.
That unmodified test passed in isolation, and an earlier complete working-tree run
also passed. It belongs to the user's preexisting uncommitted capture changes;
the isolated lighting release passes its entire suite. The remaining race is
reported without changing or committing unrelated capture implementation/tests.

The execution environment has no `/dev/serial/by-id` device, including a host-level
check. No upload, board reset, USB hotplug or physical LED observation occurred.
The new `scripts/test_rgb_serial.py` is supplied for operator hardware acceptance,
including legacy/custom colors, malformed/timeout packets, DMX progress and heap.
Existing device firmware and physical wiring are preserved. Preexisting stable-port
and capture/UI/data changes are excluded from the three lighting commits.

### Documentation and manual acceptance

- [Effects architecture, firmware migration and complete manual checklist](lighting-effects.md)
- [Linux service configuration and deployment checks](lighting-deployment.md)
- [API contract, effect parameters, examples and maintenance controls](lighting-api.md)

Before deployment, flash only the production image during maintenance, rerun legacy
and RGB console tests, observe all A–L effects, exercise capture priorities and the
10-second hold, unplug/reconnect/reset hardware, verify simulated M–P remain
unavailable on DMX RGB, and run a sustained physical soak. Electrical timing and
visible colors require direct measurement/observation. Disconnected hardware or
forced host termination cannot guarantee OFF without a device host-loss watchdog.


### Consolidated lighting commits

- Backend `7f72141`: `feat(lighting): add asynchronous effects engine and capability-aware API`.
- Frontend `138b38e`: `feat(lighting): add protected maintenance previews and zone simulation`.
- Firmware changes in this commit: `feat(firmware): add compatible RGB commands for lighting effects`.

These commit subjects also serve as commit message suggestions for follow-on
integration. Only lighting paths are included; preexisting stable-port changes in
`platformio.ini`/`scripts/test_serial.py` and unrelated backend/frontend changes
remain in their working trees.

## 2026-11-14 — Move lighting API into the ESP32 repository

The requested service boundary is now explicit: `cabek-esp32/lighting_api` owns
all lighting endpoints, effect rendering, hardware drivers and persistent serial
I/O. `python -m lighting_api --port 8001` launches it independently, with its own
requirements, private environment file and `deploy/cabek-lighting.service`.
AutoEstimate remains unchanged. The previous embedded CABEK lighting routes,
engine, drivers and serial tests were removed from the application repository;
the tests and API reference were relocated here.

CABEK AI retains only its real application readiness probe and a bounded HTTP
lifecycle client. Its capture hooks publish the latest state, capture identity,
sequence and monotonic elapsed time to authenticated `/api/v1/lights/events`.
Repeated heartbeats preserve phases and completion expiry. Slow/unavailable
lighting HTTP cannot block capture; reconnection sends the latest snapshot rather
than an obsolete event queue. Graceful application shutdown publishes OFF best
effort; forced exit/network loss retains the last state until client recovery.
The frontend now uses `VITE_LIGHTS_API_BASE_URL`; Vite routes lighting to port 8001
before forwarding ordinary API calls to CABEK. Maintenance tokens remain in memory.

Validation: **60 standalone lighting tests passed**, **32 focused application
checks passed**, and **619 frontend tests plus the production build passed**.
An in-memory cross-repository HTTP contract check verified READY → SCANNING →
COMPLETED → OFF snapshots. The full application run had **297 passed and one
previously documented intermittent capture-retry failure** in the user's unrelated
changes. No Playwright, firmware upload, physical USB access or LED observation
was performed. Firmware sources and wiring were not changed by this relocation.

Manual acceptance: start port 8001 independently, confirm CABEK's OpenAPI contains
no lighting paths, configure the application HTTP URL/control token, observe real
capture events and ten-second completion recovery, exercise the maintenance panel,
and restart each process independently. Repeat authorization, USB reconnect,
unsupported-zone and physical observation checks in the updated deployment guide.
