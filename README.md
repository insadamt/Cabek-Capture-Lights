# CABEK ESP32 DMX lighting

This repository preserves the working ESP32/MAX485 DMX transmitter and provides
RGB protocol extensions and Linux deployment for automatic lighting effects.
It depends on
PlatformIO and the sibling FastAPI backend for API/state/serial ownership.

Firmware console: 115200 baud; commands `0` OFF, `1` RED, `2` BLUE, `3` GREEN,
`4` RGB WHITE, `?` STATUS. GPIO wiring and UART2 DMX 250000-baud 8N2, address 001,
RGB channels 1–3 remain unchanged. Firmware starts OFF and continuously sends DMX.
Extended `R r g b\n` commands
add 8-bit RGB after capability negotiation; existing commands remain compatible.

- [Effects, firmware migration and manual acceptance](docs/lighting-effects.md)
- [Lighting deployment and manual checks](docs/lighting-deployment.md)
- [Backend API contract](../cabek_ai_global/docs/lighting-api.md)
- [Firmware diagnostics and development journal](docs/technical-journal.md)
- [Example automatic startup unit](deploy/cabek-tunnel.service)

Normal operation uses the backend's persistent serial bridge. Close it before
running serial diagnostics or PlatformIO Serial Monitor. New smooth effects require
firmware advertising `protocol=rgb8-v1`; legacy
firmware keeps its fixed-color lifecycle. See the migration guide before flashing.
