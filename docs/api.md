# API

## Base URL

```text
http://127.0.0.1:8001
```

The local service exposes only two POST endpoints. It requires no CABEK AI session, readiness state or bearer token. Keep it accessible only through a trusted local boundary.

## `POST /api/lights/set`

Sets a solid RGB color or starts an animation. Each request replaces the previous effect.

```http
POST /api/lights/set
Content-Type: application/json
```

### Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `effect` | string | `solid` | Effect name |
| `color` | string | `#FFFFFF` | Primary color, `#RRGGBB` |
| `brightness` | number | `100` | 0–100% |
| `speed` | number | `1` | Playback multiplier, 0.1–5 |
| `repeat` | boolean | `false` | Repeat the animation |
| `duration_ms` | integer | `2000` | Base cycle length, 1–120000 ms |
| `colors` | array | optional | Palette of 2–32 HEX colors |
| `easing` | string | `ease_in_out` | `linear`, `ease_in`, `ease_out`, `ease_in_out` |

A solid color uses `effect`, `color` and `brightness`. `colors` is available for `transition`, `color_cycle` and `cyber_morph`; `color_cycle` requires it. Named cinematic effects use their preset colors.

Recognized parameters not used by an effect are ignored; unknown fields and invalid applicable values return `422`.

### Examples

Solid red:

```json
{
  "effect": "solid",
  "color": "#FF0000",
  "brightness": 100
}
```

Repeating blue breathing:

```json
{
  "effect": "breathing",
  "color": "#0066FF",
  "brightness": 80,
  "speed": 1.5,
  "repeat": true
}
```

Multicolor cycle:

```json
{
  "effect": "color_cycle",
  "colors": ["#0066FF", "#8B00FF", "#00FFFF"],
  "brightness": 70,
  "speed": 0.8,
  "repeat": true
}
```

To try the breathing effect:

```bash
curl -X POST http://127.0.0.1:8001/api/lights/set -H 'Content-Type: application/json' -d '{"effect":"breathing","color":"#0066FF","brightness":80,"speed":1.5,"repeat":true}'
```

### Animation timing

`duration_ms` is the length of one cycle at `speed: 1`. At `speed: 2`, a 2000 ms cycle lasts one second.

A non-repeating effect keeps its final output until another command. A repeating effect continues until replaced or turned off.

See [Effects](effects.md) for the supported names and final colors.

## `POST /api/lights/off`

Cancels the active animation and turns the lights off. No body is required.

```bash
curl -X POST http://127.0.0.1:8001/api/lights/off
```

OFF takes priority over queued SET requests. A serial transaction already in progress may finish first.

## Responses

Solid color (`200`):

```json
{"success": true, "effect": "solid", "status": "active"}
```

Animation accepted (`202`):

```json
{"success": true, "effect": "breathing", "status": "running"}
```

OFF (`200`):

```json
{"success": true, "status": "off"}
```

### Errors

| Status | Meaning |
|---|---|
| `409` | A queued SET request was replaced |
| `422` | Invalid effect or parameters |
| `501` | The ESP32 firmware does not support the requested RGB output |
| `503` | A command could not be delivered to the ESP32 |

Responses confirm initial serial delivery, **not visual LED output**. Future animation frames may fail after a `202` response; those errors are logged.

There is no status, readiness, lifecycle-event or capability endpoint. Older `/api/v1/lights/*` routes have been removed.
