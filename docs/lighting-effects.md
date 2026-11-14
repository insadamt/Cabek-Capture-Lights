# Advanced lighting engine: firmware, deployment and acceptance

This guide explains the RGB protocol extension, compatible deployment and manual
acceptance of the advanced effects engine. It depends on the existing ESP32/MAX485
wiring, PlatformIO, pyserial, and the sibling FastAPI backend and React application.
The API reference is [lighting-api.md](../../cabek_ai_global/docs/lighting-api.md).

## What changed

The existing backend state manager, persistent serial owner, readiness checks,
credential boundary and capture hooks are extended with a pure effect renderer,
a hardware driver interface and memory-only zone simulation. HTTP handlers never
render in background threads of their own or wait for hardware. Rendering uses
monotonic elapsed time and at most the configured 1–20 Hz, default 15 Hz. Unchanged
frames are suppressed; one current frame replaces obsolete animation output.
Lifecycle events remain authoritative, including the cancellable 10-second
completion hold. The frontend gains `/maintenance/lights` with session-only
operator authentication. Configuration persists in the host environment file;
preview requests and animation state are intentionally ephemeral.

RGB firmware adds a bounded packet parser in `src/rgb_command.h`; the UART2 DMX
sender is unchanged. GPIO TX17, DE25, /RE26, USB UART0 pins 1/3, address 001,
channels 1–3, 250000 baud 8N2 DMX and the 115200 baud console remain unchanged.
No W wire, pixel controller or wiring change is introduced. Firmware still starts
OFF and continuously sends full 513-byte universes in the production stage.

## Extended console contract

| Request | Response / behavior |
| --- | --- |
| `0`, `1`, `2`, `3`, `4` | Unchanged OFF, RED, BLUE, GREEN, WHITE acknowledgments |
| `?` | Unchanged STATUS fields plus `protocol=rgb8-v1` |
| `R 37 99 235\n` | `OK R RGB 37 99 235`; selected command becomes `R`, status rgb=37,99,235 |
| Invalid RGB packet | `ERR RGB: use R <0-255> <0-255> <0-255>`; previous output retained |
| Incomplete RGB packet | After >250 ms without a byte, `ERR RGB timeout`; drain until newline before accepting commands |

RGB packets require `R`, whitespace before each of three decimal 0–255 channels,
and LF (CRLF accepted). Negative/fractional/excess/missing channels and overlong
packets are rejected atomically. The buffer is 32 bytes with no dynamic allocation.
Partial packet digits never become legacy color commands. The input budget remains
32 bytes per loop so DMX refresh continues while receiving partial/bad packets.
After timeout send a newline before the next legacy command or status query.
The bridge sends LF on connect and consumes a recognized stale RGB response
before validating STATUS, so an interrupted packet cannot block reconnection.
The version stays `cabek-dmx-v1` because legacy responses are compatible; capability
negotiation uses the explicit `protocol` field and image identity uses sketch MD5.

The bridge requires an exact RGB OK plus matching healthy STATUS before confirming
each changed global output. It validates production mode, baud rates, RGB bounds,
zero errors, monotonic uptime and progressing DMX frames. Firmware without the
capability field keeps its existing fixed-color behavior and refuses arbitrary
RGB/effects. Initial or disconnected capability status is unconfirmed. A reconnect
preserves logical requests and current elapsed animation phase; it never queues a
history of serial frames. At a configured brightness limit below 100%, legacy
firmware stays OFF because it cannot express a reduced output.

## Build and migrate

1. Stop the backend/other serial owner and retain the known working binary and
   hardware configuration. Existing ignored `.rollback/` evidence is local only;
   copy backups separately before moving the project. Do not erase the whole flash.
2. Build without uploading:

   ```sh
   pio run -e serial_only -e dmx_init -e esp32dev
   g++ -std=c++11 -Wall -Wextra -Werror tests/rgb_command_test.cpp -o /tmp/cabek-rgb-command-test
   /tmp/cabek-rgb-command-test
   ```

3. When ready to test on the real idle tunnel hardware, upload **only the production
   environment**, using the verified by-id port in `platformio.ini`:

   ```sh
   pio run -e esp32dev -t upload
   python scripts/test_serial.py --port /dev/serial/by-id/<verified-device> \
     --mode dmx_tx --firmware .pio/build/esp32dev/firmware.bin \
     --log .evidence/legacy-with-rgb.bin --soak-seconds 60
   python scripts/test_rgb_serial.py --port /dev/serial/by-id/<verified-device> \
     --firmware .pio/build/esp32dev/firmware.bin --soak-seconds 60
   ```

   The legacy tester deliberately resets the ESP32. The RGB tester requires an
   exclusive idle port, tests invalid/partial packets, preserves DMX refresh,
   checks resets/heap and finishes OFF. Console tests establish firmware behavior;
   independently observe the strips and measure RS485 timing before acceptance.

4. Close the tester and restart the updated backend with existing credentials and
   `CABEK_LIGHTS_DRIVER=dmx_rgb`, `CABEK_LIGHTS_UPDATE_HZ=15`. Read `/capabilities`;
   smooth RGB must be true only after `protocol=rgb8-v1` was validated. Missing USB
   must remain honest disconnected/unconfirmed status without blocking capture.
5. Build/deploy the React app with its existing public API base URL and authenticated
   gateway. Visit `/maintenance/lights`; enter the maintenance token manually.
   The token must never be compiled into a bundle, URL or browser storage.
6. To roll back, stop the backend and restore the retained known production image
   with its original boot/partition layout, then restore the matching backend
   release. The new backend also supports legacy firmware's fixed-color lifecycle.

No firmware was uploaded as part of this implementation: USB hardware was absent
from the execution environment. Physical colors, USB hotplug and long-run firmware
stability require the checklist below. Existing working on-device firmware and
wiring have therefore been preserved.

## Simulate independent zones

Use a separate development backend configuration with the existing real readiness
fixtures and private credentials:

```ini
CABEK_LIGHTS_ENABLED=1
CABEK_LIGHTS_DRIVER=simulated_pixels
CABEK_LIGHTS_PIXEL_COUNT=60
CABEK_LIGHTS_COLOR_ORDER=RGB
CABEK_LIGHTS_BRIGHTNESS_LIMIT=50
CABEK_LIGHTS_UPDATE_HZ=15
CABEK_LIGHTS_PREVIEW_SECONDS=30
```

All 16 effects appear as supported; `simulated=true`, `esp32_available=false` and
zone swatches clearly identify memory-only output. There is no serial connection.
Optional `CABEK_LIGHTS_PIXEL_MAPPING` is a permutation of 0 through zone-count−1;
`COLOR_ORDER` affects simulated physical-channel output while the API displays
logical RGB zones. `direction=reverse` reverses travel before that mapping.

The NAVIGATE 5050-60D-10MM label says 24V, 60 LEDs/m, six LEDs per cut, 14W/m,
10m roll. These specifications do not identify the controller or prove individual
LED addressability. Keep M–P unavailable on the analog DMX decoder. Verify the IC,
pinout, signal voltage, controller protocol, power supply/current injection and
actual independently controlled group size before implementing a physical driver.
Never power the 24V strip directly from an ESP32 GPIO. Brightness ceilings are
software channel limits; they are not measured electrical power protection.

## Automated verification

Run the existing suites and the new deterministic tests:

```sh
# In cabek_ai_global, with requirements-api-dev.txt installed:
python -m pytest tests -q
# In Cabek Frontend, with its existing public API base configuration:
npm test
npm run build
```

`tests/lighting/test_effects.py` checks all A–P renderers, exact interpolation,
easing, final colors, finite/repeating behavior, direction, zone mapping, brightness
ceilings, cancellation, replacement, expiry and capture priority with mock time.
`test_rgb_protocol.py` checks negotiated RGB, bad acknowledgments, deduplication,
rate limits and latest-state replay. Existing tests retain legacy commands,
pseudo-TTY reconnection, readiness/real capture hooks, failures and shutdown.
`tests/api/test_lighting_effects.py` checks auth, strict parameters, capabilities,
repeated/concurrent requests and scan conflicts. Frontend unit tests check read-only
panel loading, header credentials, safe redirects and supported payload fields.
No Playwright or browser automation is required or used.

## Manual acceptance checklist

- [ ] Retain the last working firmware; confirm by-id identity, permissions,
  exclusive ownership, decoder address 001/RGB mode and unchanged wiring.
- [ ] Flash the new production image only during maintenance. Verify initial OFF,
  readable `?`, `protocol=rgb8-v1`, matching image MD5, zero errors and growing frames.
- [ ] Run legacy commands 0–4 and the RGB serial tester; observe real RGB colors,
  custom colors, 0/50/100% brightness, invalid/partial packets and continuous DMX.
- [ ] In idle READY, preview all A–L effects; check smoothness/easing, fades ending
  off, breathing bounds, pulse count/interval, blue/cyan/purple morph, awakening,
  target lock, success hold, amber warning and shutdown. Adjust update rate only
  within documented limits; inspect serial/DMX health during a sustained soak.
- [ ] Rapidly switch effects and repeat identical requests. Confirm one current
  output, no preview restart/deadline extension and automatic restoration at expiry.
- [ ] Stop a preview and confirm a smooth return to lifecycle white. Verify preview
  controls reject invalid ranges, unsupported fields, missing/bad/control tokens.
- [ ] Observe BOOTING → INITIALIZING → READY from real readiness checks; refresh
  or navigate the frontend and verify no startup replay or hardware command.
- [ ] Start real photo capture during a preview or startup. Confirm Target Lock →
  red pulses, maintenance conflicts, green only after validated completion,
  then white after exactly the backend's 10-second hold plus the 800 ms transition.
- [ ] Start another capture during green/transition; confirm old timers cannot
  replace it. Fail/interrupt capture; verify amber warning and no success green.
- [ ] Disconnect/reconnect USB and reset the ESP32 during steady and animated
  output. Check current acknowledgment clears, bounded retries, honest errors and
  current-phase replay; verify no queued obsolete animation or duplicate boot.
- [ ] Start without ESP32; verify capture/API remain usable and capability status
  stays unconfirmed. Connect later and observe negotiation/current-state recovery.
- [ ] Request M–P on `dmx_rgb`; expect explicit unsupported-capability 409 responses.
  In separate simulation, inspect reveal/chase/rainbow/scanner, forward/reverse,
  zone counts/mapping/order and brightness ceiling; confirm no physical connection.
- [ ] Verify `/maintenance/lights` shows controls only with maintenance permission,
  disables them during capture, explains capability limits and shows simulation
  distinctly. Test keyboard/mobile access, logout/refresh and no stored credential.
- [ ] Stop the backend gracefully and observe dim-blue fade to OFF. Reboot the
  tunnel host to verify the installed service still starts with readiness checks.
- [ ] Run a longer physical soak with the decoder connected. Check no crashes,
  resets, heap decline, corrupt console or frame stalls; measure RS485 timing with
  a scope/logic analyzer if acceptance requires electrical timing evidence.

A serial acknowledgment cannot prove visible color, smoothness or electrical
waveforms. Unplugged hardware may retain its last output; forced process exit
cannot guarantee OFF because the preserved firmware has no host-loss watchdog.
