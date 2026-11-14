# CABEK ESP32 lighting service and firmware

This repository owns the lighting REST API, effects engine, persistent USB serial
connection and ESP32/MAX485 firmware. It depends on Python/FastAPI/pyserial for the
host service and PlatformIO for firmware. CABEK AI publishes lifecycle events as
an HTTP client; AutoEstimate does not host or control these APIs.

The lighting server runs separately on **http://127.0.0.1:8001**. Endpoints:
`/api/v1/lights/status`, `/capabilities`, `/effects`, `/stop`, `/state`, `/test`
and the authenticated application lifecycle `/events` endpoint.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-lighting.txt
cp .env.example .env
# Set private control/maintenance tokens and the verified serial port in .env.
.venv/bin/python -m lighting_api --port 8001
```

Use one server process and close serial monitors before starting it. The service
loads this repository's `.env`; environment variables take precedence. CABEK AI
runs separately, with `CABEK_LIGHTS_ENABLED=1`,
`CABEK_LIGHTS_API_URL=http://127.0.0.1:8001` and the matching control token.
The frontend maintenance panel uses `VITE_LIGHTS_API_BASE_URL` and a manually
entered maintenance token. Application refreshes never restart lifecycle effects.

Firmware wiring remains TX17, DE25, /RE26; DMX is UART2 250000 baud 8N2, address
001 and RGB slots 1–3. Console commands 0–4 and `?` remain compatible. Negotiated
`R r g b\n` packets add global RGB. Physical pixel hardware remains unverified;
progressive effects run only with the explicit memory simulation driver.

- [Lighting API and curl examples](docs/lighting-api.md)
- [Effects and firmware migration/manual checklist](docs/lighting-effects.md)
- [Host deployment](docs/lighting-deployment.md)
- [Technical journal](docs/technical-journal.md)

```sh
.venv/bin/pip install -r requirements-lighting-dev.txt
.venv/bin/python -m pytest
pio run -e serial_only -e dmx_init -e esp32dev
```
