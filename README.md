# CABEK Tunnel Lights

A small lighting controller for the exterior of the CABEK AI inspection tunnel. It receives HTTP commands and controls an RGB LED strip through an ESP32 and a DMX512 decoder.

The lighting service runs independently of CABEK AI. It does not need cameras, vehicle data or application readiness to accept a command.

## Technology

- Python 3.11+, FastAPI and pyserial
- ESP32 DevKit V1 with PlatformIO firmware
- MAX485, DMX512 RGB decoder and a conventional RGB strip

## How it works

```text
CABEK AI or a local HTTP client
            ↓
       Lighting API
            ↓
      USB serial / ESP32
            ↓
      MAX485 / DMX512
            ↓
          RGB strip
```

One worker handles serial commands and animations. A new request replaces the current effect; OFF stops it.

See [Architecture](docs/architecture.md) for the code layout.

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-lighting.txt
cp .env.example .env
```

Set `CABEK_LIGHTS_PORT` in `.env` to the ESP32's stable `/dev/serial/by-id/...` path, then start the service:

```bash
.venv/bin/python -m lighting_api --port 8001
```

Only one process can use the USB serial port. Close Serial Monitor before starting the API.

## API

The service provides **two endpoints**, both on `http://127.0.0.1:8001`:

```text
POST /api/lights/set    Color or animation
POST /api/lights/off    Stop and turn off
```

Turn the lights red:

```bash
curl -X POST http://127.0.0.1:8001/api/lights/set -H 'Content-Type: application/json' -d '{"color":"#FF0000"}'
```

Turn them off:

```bash
curl -X POST http://127.0.0.1:8001/api/lights/off
```

See [API](docs/api.md) for parameters and [Effects](docs/effects.md) for animations.

## Tests

```bash
.venv/bin/pip install -r requirements-lighting-dev.txt
.venv/bin/python -m pytest -q
pio run -e serial_only -e dmx_init -e esp32dev
```

The automated tests do not verify the physical LEDs. Flashing firmware is a separate, manual step.

## Documentation

- [Architecture](docs/architecture.md)
- [API](docs/api.md)
- [Effects](docs/effects.md)
- [Hardware](docs/hardware.md)
- [Deployment](docs/deployment.md)
- [Technical journal](docs/technical-journal.md)

The HTTP service has no authentication and binds to localhost by default. **Do not expose it directly to the LAN or Internet.**
