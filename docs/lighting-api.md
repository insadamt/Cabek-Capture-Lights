# Lighting API

Control the entire analog RGB strip with two POST routes on
`http://127.0.0.1:8001`. Depends only on the serial-connected ESP32. No CABEK AI
session, readiness check, credentials or request lifecycle is required.

## POST `/api/lights/set`

An empty JSON object selects solid white at full brightness.

| Parameter | Default | Values |
| --- | --- | --- |
| `effect` | `solid` | Names below |
| `color` | `#FFFFFF` | `#RRGGBB` |
| `brightness` | `100` | Number, 0–100 percent |
| `speed` | `1` | Number, 0.1–5 |
| `repeat` | `false` | Boolean |
| `duration_ms` | `2000` | Integer, 1–120000 |
| `colors` | Absent | Array of 2–32 HEX colors |
| `easing` | `ease_in_out` | `linear`, `ease_in`, `ease_out`, `ease_in_out` |

Only parameters relevant to the selected effect are validated. Recognized,
irrelevant parameters are ignored; unknown fields are rejected. `solid` uses only
color and brightness. All animations use brightness, duration, speed, repeat and
easing. Color applies to fades, breathing, pulse and transition. Named sequences
use their established colors. `colors` applies to transition, color_cycle and
cyber_morph; color_cycle requires it.

| Effect | Behavior / finite final output |
| --- | --- |
| `solid` | Hold the chosen color indefinitely |
| `fade_in`, `fade_out` | Fade up to the color / down to black |
| `breathing` | Smooth dark → color → dark |
| `pulse` | Brief color pulse then dark interval; finishes black |
| `transition` | Current acknowledged RGB → color, or through supplied colors; holds last |
| `color_cycle` | Through supplied colors and back to first |
| `cyber_morph` | Blue → cyan → purple → blue; optional replacement palette |
| `system_awakening` | Increasing blue startup pulses; holds blue |
| `target_lock` | White → orange → red with lock pulses; holds red |
| `mission_complete` | Current RGB → green success pulses; holds green |
| `warning` | Amber pulse; finishes black |
| `shutdown` | Current RGB → dim blue → black |

Brightness scales the output of every effect. Duration defines one **whole cycle**;
playback seconds = duration_ms / 1000 / speed. A 2000 ms animation at speed 2
finishes in one second. Repeat loops the cycle indefinitely, without an expiry
or automatic shutdown. Finite animations hold their final color until changed.

```sh
export LIGHTS=http://127.0.0.1:8001/api/lights
curl -X POST "$LIGHTS/set" -H 'Content-Type: application/json' \
  -d '{"effect":"solid","color":"#FF0000","brightness":100}'
curl -X POST "$LIGHTS/set" -H 'Content-Type: application/json' \
  -d '{"effect":"breathing","color":"#0066FF","brightness":80,"speed":1.5,"repeat":true}'
curl -X POST "$LIGHTS/set" -H 'Content-Type: application/json' \
  -d '{"effect":"color_cycle","colors":["#0066FF","#8B00FF","#00FFFF"],"brightness":70,"speed":0.8,"repeat":true,"easing":"ease_in_out"}'
```

## POST `/api/lights/off`

No body. Cancels the animation and prioritizes a legacy `0` command. OFF takes
precedence over queued SET commands; an in-flight serial transaction can finish
before OFF is acknowledged. A later SET can start a new effect.

```sh
curl -X POST "$LIGHTS/off"
```

## Responses

- `200` solid: `{"success":true,"effect":"solid","status":"active"}`
- `202` animation: `{"success":true,"effect":"breathing","status":"running"}`
- `200` OFF: `{"success":true,"status":"off"}`
- Errors: `{"success":false,"error":{"code":"hardware_unavailable","message":"..."}}`

`422` means invalid relevant parameters; `501` means RGB firmware is unsupported;
`503` means a command could not be delivered; `409` means a queued SET was
superseded. Initial delivery requires the matching serial acknowledgment.
HTTP waits only for initial delivery, never for animation completion. A successful
animation response means accepted and scheduled, not that future frames or visible
LEDs were verified. Later errors are logged; the worker reconnects and replays the
latest frame. Rejected SET requests are not activated later. Failed OFF requests
remain cancelled and retry OFF after reconnection.

There are no status, preview, capability, state or event routes. The retired
`/api/v1/lights/*` endpoints return 404. CABEK AI owns automatic lighting commands in its backend. The settings page sends manual tests through CABEK AI at
`/api/settings/lights/set` and `/api/settings/lights/off`; the browser never calls
this service directly. Local HTTP diagnostics remain available.
