# CABEK ESP32 DMX lighting

This repository preserves the working ESP32/MAX485 DMX transmitter and provides
Linux deployment instructions for automatic application lighting. It depends on
PlatformIO and the sibling FastAPI backend for API/state/serial ownership.

Firmware console: 115200 baud; commands `0` OFF, `1` RED, `2` BLUE, `3` GREEN,
`4` RGB WHITE, `?` STATUS. GPIO wiring and UART2 DMX 250000-baud 8N2, address 001,
RGB channels 1–3 remain unchanged. Firmware starts OFF and continuously sends DMX.

- [Lighting deployment and manual checks](docs/lighting-deployment.md)
- [Backend API contract](../cabek_ai_global/docs/lighting-api.md)
- [Firmware diagnostics and development journal](docs/technical-journal.md)
- [Example automatic startup unit](deploy/cabek-tunnel.service)

Normal operation uses the backend's persistent serial bridge. Close it before
running serial diagnostics or PlatformIO Serial Monitor. No reflash is required
for the lighting integration.
