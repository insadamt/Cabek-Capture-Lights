# CABEK Tunnel Lights

Local lighting control for **CABEK AI**. The application sends scan events to a small HTTP service, which controls the tunnel's exterior RGB lights through an ESP32.

```text
CABEK AI → Lighting API (:8001) → USB → ESP32 → MAX485 → DMX decoder → RGB strip
```

The lights signal the tunnel's state: blue during startup, white when ready, red during capture, green on success, and amber on errors.

## Run locally

Requires Python 3.11+ and the connected ESP32 (or the simulation driver).

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-lighting.txt
cp .env.example .env
```

Edit `.env`: set **two different tokens of at least 32 characters**, verify `CABEK_LIGHTS_PORT` (prefer `/dev/serial/by-id/...`), and use `CABEK_LIGHTS_DRIVER=dmx_rgb` for the real strip. Then:

```sh
.venv/bin/python -m lighting_api --port 8001
```

Use one lighting service process. Close PlatformIO Serial Monitor and any other program using the ESP32 port.

To inspect it, send an authenticated request:

```sh
curl -H "Authorization: Bearer $CABEK_LIGHTS_TOKEN" http://127.0.0.1:8001/api/v1/lights/status
```

CABEK AI runs separately and sends lifecycle events to this service. It needs `CABEK_LIGHTS_API_URL=http://127.0.0.1:8001` and the same control token.

## What works today

- Fixed colors and global RGB effects on the **existing DMX strip**. Smooth effects require ESP32 firmware advertising `protocol=rgb8-v1`.
- A protected maintenance page in CABEK AI at `/maintenance/lights` for previewing supported effects.
- Progressive/chase/pixel effects **in simulation only**. The NAVIGATE 24V “Magic RGB” strip has not yet been verified or connected to a compatible pixel controller.

## Guides

- [API and example requests](docs/lighting-api.md)
- [Effects and hardware limits](docs/lighting-effects.md)
- [Ubuntu deployment](docs/lighting-deployment.md)
- [Project journal](docs/technical-journal.md)

For development checks:

```sh
.venv/bin/pip install -r requirements-lighting-dev.txt
.venv/bin/python -m pytest -q
pio run -e serial_only -e dmx_init -e esp32dev
```
