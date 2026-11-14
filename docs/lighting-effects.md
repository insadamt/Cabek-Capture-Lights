# Lighting effects

CABEK AI's exterior lights communicate what the tunnel is doing. The backend selects **one active effect**; new capture events take priority over manual previews.

## Automatic sequence

| Tunnel state | Light behavior |
| --- | --- |
| Starting | Blue system-awakening pulses |
| Initializing | Slow blue breathing |
| Ready | Smooth transition to white |
| Capturing | White → orange → red, then red pulses |
| Completed | Green success pulse, hold for 10 seconds, return to white |
| Capture error | Slow amber warning |
| Shutdown | Fade to blue, then off |

Frontend refreshes do not restart this sequence. Another scan cancels the previous green countdown.

## Available effects

**On confirmed global RGB firmware** (`protocol=rgb8-v1`):

| Effect | What it looks like |
| --- | --- |
| `solid` | One steady color |
| `fade_in`, `fade_out` | Gradually brighten or dim |
| `breathing` | Gentle repeating brightness change |
| `pulse` | Configurable pulses |
| `transition` | Smooth change between colors |
| `cyber_morph` | Blue, cyan and purple transitions |
| `system_awakening` | Startup blue pulses |
| `target_lock` | White → orange → red |
| `mission_complete` | Green success animation |
| `warning` | Amber warning pulse |
| `shutdown` | Fade to off |

**Simulation only**, until independently controllable zones are verified: `progressive_reveal`, `chase`, `rainbow_wave` and `scanner_sweep`.

The existing analog RGB decoder changes the **whole strip together**. It cannot light successive physical LEDs or zones. The NAVIGATE 24V Magic RGB strip's IC and signal protocol are unverified. Do not connect it to ESP32 GPIO or assume WS2811 compatibility.

## Preview an effect

Open CABEK AI's protected `/maintenance/lights` page, or use the [API](lighting-api.md). The panel shows which effects the connected hardware supports.

Typical request:

```json
{
  "effect": "transition",
  "color": "#EF4444",
  "duration_ms": 1500,
  "brightness": 80,
  "easing": "ease_in_out"
}
```

Colors use `#RRGGBB`; brightness is a percentage. Preview requests have a configurable timeout (30 seconds by default), even when repeating. Effects never override an active scan.

## ESP32 firmware

Legacy serial commands remain: `0` off, `1` red, `2` blue, `3` green, `4` white and `?` status. Updated firmware also accepts `R 37 99 235` followed by a newline for custom RGB and reports `protocol=rgb8-v1` in status.

GPIO and DMX wiring stay unchanged: **TX GPIO17, DE GPIO25, /RE GPIO26**; USB serial 115200 baud, DMX UART2 250000 baud / 8N2, address 001, channels 1–3. White is created using RGB, not a dedicated W wire.

Only flash the updated production firmware during a controlled maintenance window, after retaining the current working image:

```sh
pio run -e esp32dev
pio run -e esp32dev -t upload
```

The firmware extension was built and tested in software, but physical smooth effects and the new protocol still require on-device acceptance. Keep the old working firmware until you are ready to test.

## Acceptance checks

- Verify physical red/blue/green/white, custom colors and smooth fades.
- Confirm startup → ready → capture → green (10 s) → white.
- Check that a failed capture shows amber, not success green.
- Test disconnection/reconnection and that preview cannot interrupt scanning.
- Request a progressive effect on the physical RGB driver: it must be rejected, not faked.

Serial acknowledgments do not establish observed light behavior. For rollout and recovery, use the [deployment guide](lighting-deployment.md).
