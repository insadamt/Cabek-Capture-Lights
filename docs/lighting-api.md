# Lighting effects API

This guide defines the backend-owned exterior lighting engine, authenticated API,
configuration and hardware migration. It depends on FastAPI, one pyserial worker,
the existing capture lifecycle and this repository’s `lighting_api` package and firmware.

## Ownership and hardware compatibility

The existing chain remains CABEK AI HTTP client → this standalone FastAPI service → USB serial → ESP32 → MAX485
→ RGB DMX decoder → ordinary RGB strip. DMX stays on UART2 TX17, DE25, /RE26,
250000 baud, 8N2, address 001, channels 1–3. RGB white uses three channels; no W
wire or physical wiring changes are needed. Lights are outside the photo tunnel.

`LightingState` remains authoritative. `LightingEngine` chooses one effect and
renders from monotonic elapsed time; `lighting_effects` and `lighting_pixels` are
pure functions. `LightingDriver` adapts those frames to `DmxRgbDriver` or an explicit
`SimulatedPixelDriver`. This service’s worker alone owns serial I/O; HTTP requests
only change desired state. The existing independent readiness worker remains.
There are no effect-specific threads, timers, command queues or browser events.
Slow or absent hardware never waits inside a lighting HTTP handler.

| Driver/firmware | Available output |
| --- | --- |
| `dmx_rgb`, legacy status without `protocol=rgb8-v1` | Existing fixed colors, boot blink, capture red/green/white and `/test`; custom RGB/effects rejected |
| `dmx_rgb`, confirmed `protocol=rgb8-v1` | Global RGB effects A–L, 8-bit RGB, software brightness, smooth transitions |
| `simulated_pixels` | All effects in memory, including M–P; no serial port or physical LEDs |

Before connection, RGB extension capability is unconfirmed and effect requests
are rejected explicitly. Loss of connection clears confirmation, keeps requested
lifecycle/preview state, and retries with bounded backoff. Reconnection negotiates
again, terminates an interrupted RGB packet with LF, and renders the **current elapsed phase**, rather than replaying obsolete
frames or restarting startup. A preview still expires during an outage.

The 24V NAVIGATE 5050-60D-10MM strip is **unverified hardware**. Its controller IC,
wiring, grouped addressability, signal level and protocol require investigation.
No WS2811 driver is installed. The analog RGB decoder cannot address zones. Never
power the strip from GPIO or enable simulated zone effects on that decoder.
`pixel_count` currently means logical independent zones in simulation; individual
physical LED control is never asserted. A zone may later represent a verified
hardware group. Confirm its protocol and electrical/power requirements first.

## Application lifecycle and priorities

| Backend event | RGB-capable effect |
| --- | --- |
| Launcher BOOTING | System Awakening, starts off and rises through subtle blue pulses |
| Lifespan INITIALIZING | Repeating blue breathing |
| Actual dependencies ready | 800 ms transition to white |
| Capture admitted | 1200 ms Target Lock, white → orange → red, short pulse |
| Capture still active | Repeating smooth red pulses |
| All originals saved and validated | Mission Complete → green, success pulse, hold green |
| 10 seconds after completion | Transition to white if ready, otherwise initialization effect |
| Capture fails/interrupted | Slow amber warning; never success green |
| Graceful shutdown / OFF | Current output → dim blue → off in 1000 ms |

The state enum remains `BOOTING`, `INITIALIZING`, `READY`, `SCANNING`, `COMPLETED`,
`OFF`. Warning is an effect with the failed lifecycle state, not fabricated
completion. A new capture, actual state transition or explicit idle READY request
clears warning. OFF stays off until an authorized transition or actual capture.
READY requires real provider/models/supervisor/storage readiness. Very fast startup
can finish before an awakening animation is visible; no fake startup delay is added.

Actual capture events have priority over every preview and decorative effect.
Capture identities reject overlapping owners and ignore stale/duplicate finishes.
A new capture cancels the previous completion deadline. Browser reads, refreshes
and navigation never start or restart lighting. These events describe physical
photo delivery; the separate AI inference job is not used to fabricate capture
success. Readiness failures cannot interrupt an active capture's ownership.

Maintenance preview starts only in idle healthy READY, expires after the configured
preview timeout (even when `repeat=true`), and is replaced atomically. An identical
active request is idempotent and does not extend its deadline or restart its phase.
A different request replaces it; `/stop` returns smoothly to lifecycle white.
Lifecycle changes cancel a preview. Stop/test/state overrides during capture are
409 conflicts. Stop never aborts a scan or turns capture lights off.

## Configuration and persistence

Install `requirements-lighting.txt` in this repository. Lighting stays opt-in and requires two distinct
host-only tokens of at least 32 characters. Persist configuration in the existing
private lighting service `.env` or systemd environment file and restart after changes;
process environment takes precedence. Previews and lifecycle events are ephemeral,
so a process restart performs readiness again instead of replaying saved success.
Never put lighting tokens in `VITE_*`, source files, URLs or browser storage.

| Environment variable | Default | Limits / purpose |
| --- | --- | --- |
| `CABEK_LIGHTS_ENABLED` | `0` | `1` enables lighting |
| `CABEK_LIGHTS_DRIVER` | `dmx_rgb` | Only `dmx_rgb` or `simulated_pixels` accepted |
| `CABEK_LIGHTS_PORT` | `auto` | Explicit `/dev/serial/by-id/...` preferred; auto requires exactly one by-id device |
| `CABEK_LIGHTS_BAUD` | `115200` | Must match firmware console |
| `CABEK_LIGHTS_TOKEN` | empty | Control/status bearer token |
| `CABEK_LIGHTS_MAINTENANCE_TOKEN` | empty | Separate maintenance bearer token |
| `CABEK_LIGHTS_TIMEOUT` | `1` | Serial response/write timeout, >0 and ≤60 s |
| `CABEK_LIGHTS_RECONNECT_SECONDS` | `2` | Retry backoff, >0 and ≤60 s |
| `CABEK_LIGHTS_HEALTH_SECONDS` | `5` | Firmware/application health interval, >0 and ≤60 s |
| `CABEK_LIGHTS_UPDATE_HZ` | `15` | 1–20 Hz; upper bound respects round-trip serial and ~40 Hz DMX |
| `CABEK_LIGHTS_PREVIEW_SECONDS` | `30` | 1–120 s automatic preview cutoff |
| `CABEK_LIGHTS_BRIGHTNESS_LIMIT` | `100` | 0–100% output multiplier / channel ceiling; legacy firmware stays OFF when below 100 |
| `CABEK_LIGHTS_PIXEL_COUNT` | `60` | 1–1024 logical simulated zones |
| `CABEK_LIGHTS_PIXEL_MAPPING` | empty | Optional comma-separated permutation of all zone indices |
| `CABEK_LIGHTS_COLOR_ORDER` | `RGB` | Any permutation of RGB; simulated physical channel mapping only |

The brightness limit scales both global output and zone frames. It bounds channel
levels, not measured watts/current: choose electrical power limits from verified
strip/controller specifications before future physical pixel implementation.
A future verified controller plugs into `LightingDriver` with bounded synchronous
methods on the existing worker; animation logic and HTTP routes remain unchanged.

Use **one lighting API process**, without reload or multiple workers. Close all serial
monitors/diagnostic scripts before enabling the service. No competing standalone
serial service should run. The lighting launcher binds `127.0.0.1:8001` by default. Protect **all**
existing capture routes through the trusted local boundary/authenticated gateway;
CORS alone is not authentication. Allowed frontend origins accept Authorization.

## HTTP contract

Every endpoint is below `/api/v1/lights` and requires `Authorization: Bearer ...`.
Control and maintenance tokens may read and request permitted lifecycle states;
only the maintenance token may start/test/stop previews. No new duplicate routes
replace the existing `/status`, `/state` or `/test`.

| Method/path | Result |
| --- | --- |
| `GET /status` | 200 desired lifecycle, current rendered frame and separate driver confirmation |
| `GET /capabilities` | 200 actual negotiated capability flags and caller's `can_preview` permission |
| `GET /effects` | 200 all 16 effects, compatibility, accepted parameters/defaults/limits |
| `POST /effects` | 202 accept one validated maintenance preview |
| `POST /stop` | 202 cancel preview/test and restore lifecycle; optional empty JSON body |
| `POST /state` | 202 existing authorized transition, e.g. `{"state":"OFF"}` |
| `POST /test` | 202 existing 3-second fixed-color test, e.g. `{"color":"RED"}` |

Effects accept only parameters listed for that effect. `color` and `from_color`
use `#RRGGBB`; `brightness` is 0–100%, `min_brightness` is 0–brightness,
`duration_ms` is 100–120000, and easing is `linear`, `ease_in`, `ease_out` or
`ease_in_out`. Unknown fields, irrelevant parameters, invalid ranges, boolean
numbers and string booleans are rejected. RGB and brightness are independent:
`color=#FF0000, brightness=50` emits RGB 128,0,0 before any configured limit.

| Effect | Accepted parameters (defaults shown where useful) |
| --- | --- |
| `solid` | color `#2563EB`, brightness `80` |
| `fade_in`, `fade_out` | color, brightness, duration_ms `2000`, easing `ease_in_out`; fade_out uses current output when color is omitted |
| `breathing` | color, min_brightness `5`, brightness (maximum), duration_ms (full cycle), repeat `false` |
| `pulse` | color, brightness (intensity), pulse_duration_ms `500` (100–10000), interval_ms `500` (0–10000), count `3` (1–100), repeat |
| `transition` | from_color (current rendered output if omitted), color (destination), brightness, duration_ms, easing |
| `cyber_morph` | duration_ms per blue/cyan/purple leg, brightness, repeat |
| `system_awakening`, `target_lock`, `mission_complete`, `shutdown` | duration_ms, brightness |
| `warning` | duration_ms (amber cycle), brightness, repeat |
| `progressive_reveal` | color, brightness, duration_ms, direction, repeat |
| `chase`, `scanner_sweep` | color, brightness, speed `2` (0.1–30 zones/s), direction, segment_length `5` (1–1024, ≤zone count), repeat |
| `rainbow_wave` | brightness, speed, direction, repeat |

Direction is `forward` or `reverse`. Rainbow speed measures phase travel in zones/s.
Scanner duration is a round trip; chase includes entrance/exit travel. Non-repeated
sequences retain their last rendered frame until replaced or preview expiry.
Finite pulse ends off; finite breathing ends at minimum; reveal retains all zones;
scanner returns to its initial end; rainbow completes one phase cycle.
The timeout can intentionally end an effect before its full requested duration.

`status.color` identifies the current desired rendered RGB as a legacy name or hex string;
`rgb` is current effective output, `brightness` includes the configured limit,
`active_effect` names the renderer, `preview_active`/`requested_effect` describe the
logical preview. `pixels` contains logical frames only for zone simulation.
`simulated=true` explicitly marks memory output; `esp32_available=false` in that
mode even if the simulator is connected. `acknowledged_rgb` is the last confirmed
global frame (null for zone frames/disconnection). `synchronized` compares current
desired output with confirmed output; continuously changing animations may be
between updates. `capability_error` explains unavailable RGB negotiation.
`firmware`, `last_seen_at` and `last_successful_command` are historical during
outages; current acknowledgment clears. **202 means accepted, never observed LED
output.** Driver confirmation and simulated frames do not prove physical color.

Errors keep `{"error":{"code":"...","message":"..."}}`: 401 missing/bad
credential, 403 maintenance required, 409 ownership/readiness/transition conflict,
409 `lighting_unsupported_capability`, 422 invalid JSON/parameters/segment length,
503 lighting disabled. SCANNING/COMPLETED cannot be fabricated through `/state`.
A hardware outage accepts permitted logical state changes and reports failure.

## Examples and maintenance panel

Set `LIGHTS_BASE=http://127.0.0.1:8001/api/v1/lights` and provide local tokens via
shell variables. Use the real deployment address; never save actual secrets.

```sh
curl -sS -H "Authorization: Bearer $LIGHTS_TOKEN" "$LIGHTS_BASE/capabilities"
curl -sS -H "Authorization: Bearer $LIGHTS_TOKEN" "$LIGHTS_BASE/effects"
curl -sS -H "Authorization: Bearer $LIGHTS_MAINTENANCE_TOKEN" \
  -H 'Content-Type: application/json' -d '{"effect":"breathing","color":"#2563EB","duration_ms":2000,"brightness":80,"repeat":true}' \
  "$LIGHTS_BASE/effects"
curl -sS -H "Authorization: Bearer $LIGHTS_MAINTENANCE_TOKEN" \
  -H 'Content-Type: application/json' -d '{"effect":"transition","from_color":"#0000FF","color":"#FF0000","duration_ms":1500,"easing":"ease_in_out"}' \
  "$LIGHTS_BASE/effects"
# Zone simulation only; this returns 409 on global RGB hardware.
curl -sS -H "Authorization: Bearer $LIGHTS_MAINTENANCE_TOKEN" \
  -H 'Content-Type: application/json' -d '{"effect":"chase","color":"#00AAFF","speed":2,"segment_length":5,"direction":"forward","repeat":true}' \
  "$LIGHTS_BASE/effects"
curl -sS -X POST -H "Authorization: Bearer $LIGHTS_MAINTENANCE_TOKEN" "$LIGHTS_BASE/stop"
curl -sS -H "Authorization: Bearer $LIGHTS_TOKEN" "$LIGHTS_BASE/status"
```

Open `/maintenance/lights` in the existing React app, authenticate with the
maintenance token, and select supported effects/color/brightness/duration. Controls
are shown only after server authorization; the backend enforces that permission on
every write. The panel uses existing base surfaces/buttons and French labels.
It polls reads once per second without overlapping requests, displays connection
and capability restrictions, and shows logical zone swatches only in simulation.
Login/refresh/logout never issues an effect or lifecycle command. Logout drops the
in-memory credential; an existing preview expires server-side or can be stopped
before logout. The API must still have its real capture dependencies ready.

See [firmware migration and manual acceptance](lighting-effects.md)
and [Linux service installation](lighting-deployment.md).


## Service boundary and lifecycle events

All routes above are implemented in **this repository**, under `lighting_api`.
Run `python -m lighting_api --port 8001` independently of CABEK AI. CABEK AI has
no lighting routes, effect renderer or serial driver; its small HTTP client sends
`POST /api/v1/lights/events` with the server-side control bearer credential.
The frontend uses `VITE_LIGHTS_API_BASE_URL` (default localhost:8001); Vite proxies
lighting routes separately before its ordinary CABEK API proxy. Production direct
browser access requires `CABEK_LIGHTS_CORS_ORIGINS`, or use an authenticated gateway.

A lifecycle snapshot contains `session_id` (application process identity),
`sequence` (increasing integer), `state`, `ready`, `capture_id` (required only for
SCANNING), `elapsed_ms` (monotonic time in this state) and `warning`. Example:

```json
{"session_id":"application-process-uuid","sequence":12,"state":"SCANNING",
 "ready":true,"capture_id":"actual-capture-id","elapsed_ms":1250,"warning":false}
```

Only trusted application services should publish events; these credentials also
permit lifecycle control. Repeated/stale sequence numbers from the same session
are ignored. Heartbeats preserve animation phase and the original completion
expiry; a service restart receives the latest snapshot with elapsed time rather
than replaying an event queue. One authoritative application process is supported.
A new process identity replaces the previous lifecycle owner. A disconnected client
cannot command shutdown: the service retains the most recently received state
until the application recovers. No heartbeat-loss shutdown watchdog is introduced.

CABEK AI settings: `CABEK_LIGHTS_ENABLED=1`, `CABEK_LIGHTS_API_URL=http://127.0.0.1:8001`,
`CABEK_LIGHTS_TOKEN=<matching-control-token>`. Serial/driver/maintenance settings
belong exclusively to this repository’s service environment. No pricing or model
dependency is needed to run the standalone server; normal READY comes from the
application’s real readiness checks. For isolated simulation tests, a trusted
operator can submit an authenticated READY event with `ready=true`.
