# Architecture

## Service role

CABEK Tunnel Lights is a standalone controller. It turns HTTP requests into serial commands for the ESP32 and calculates color changes for animations.

It does **not** decide when a vehicle scan starts or finishes. CABEK AI owns those decisions and calls the lighting API when it wants a new color or effect.

## Control flow

```text
CABEK AI backend / local client
              ↓ HTTP
        FastAPI (:8001)
              ↓
       Lighting service
       ├── Command queue
       └── Animation worker
              ↓
      Persistent USB serial
              ↓
             ESP32
              ↓ DMX512 via MAX485
       RGB decoder / strip
```

Only the lighting worker writes to serial. The connection stays open between commands and reconnects when needed.

A `/set` request replaces the previous effect. `/off` cancels it and takes priority over queued SET commands. HTTP waits for the **initial serial acknowledgment**, not for an entire animation to finish.

## Application integration

CABEK AI can use the same two routes for automatic lights and manual tests.

| Application event | Suggested command |
|---|---|
| Startup | `system_awakening` |
| Ready | Solid white |
| Capture starts | Repeating red `pulse` |
| Capture finishes | `mission_complete` |
| Ten seconds later | Solid white |
| Capture fails | `warning` |
| Shutdown | `/off` |

The ten-second delay belongs to CABEK AI, not the lighting service. No readiness event or lifecycle API exists in this repository.

The CABEK AI settings page calls its own backend, which forwards approved requests to the local lighting service. The browser should not access the USB controller directly.

## Code layout

```text
lighting_api/
  main.py                 FastAPI app
  lighting_routes.py      Set / off endpoints
  lighting_service.py     Command queue and worker
  lighting_effects.py     Effect validation and rendering
  lighting_protocol.py    ESP32 serial commands
  lighting_config.py      Environment settings
  errors.py               API error responses

src/                      ESP32 firmware and DMX output
deploy/                   systemd unit examples
tests/                    API, serial and effect tests
```

The current decoder controls the whole RGB strip together. Independent LED zones are not supported.

See [API](api.md), [Effects](effects.md) and [Hardware](hardware.md).
