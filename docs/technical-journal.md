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
