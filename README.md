# CABEK Tunnel Lights

Standalone local RGB control: FastAPI → one animation worker → USB Serial → ESP32
→ MAX485 → analog DMX512 RGB decoder. Depends on Python 3.11+, pyserial and USB
access. CABEK AI is optional; there are no camera or readiness requirements.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-lighting.txt
cp .env.example .env
# Set CABEK_LIGHTS_PORT to your /dev/serial/by-id/... device.
.venv/bin/python -m lighting_api --port 8001
```

Keep one process and close Serial Monitor. The server binds to `127.0.0.1`.
Do not publish unauthenticated hardware controls to the LAN or Internet.

```sh
curl -X POST http://127.0.0.1:8001/api/lights/set \
  -H 'Content-Type: application/json' -d '{"color":"#FF0000"}'
curl -X POST http://127.0.0.1:8001/api/lights/off
```

Exactly two routes: `POST /api/lights/set` and `POST /api/lights/off`.
New commands replace the active effect. Finite effects hold their final color;
repeating effects continue until replaced or stopped. Animations/custom colors
require RGB firmware; legacy full-strength colors remain available without it.

- [API reference and examples](docs/lighting-api.md)
- [Hardware, firmware and manual checks](docs/lighting-effects.md)
- [Local deployment and CABEK AI integration](docs/lighting-deployment.md)
- [Technical journal](docs/technical-journal.md)

Software checks use mocked firmware and a Linux pseudo-TTY, without touching USB:

```sh
.venv/bin/pip install -r requirements-lighting-dev.txt
.venv/bin/python -m pytest -q
c++ -std=c++11 -Isrc tests/rgb_command_test.cpp -o /tmp/cabek-rgb-test
/tmp/cabek-rgb-test
```

Firmware is preserved. To build all diagnostic stages when PlatformIO is installed:
`pio run -e serial_only -e dmx_init -e esp32dev`. Flashing is a separate manual step.
