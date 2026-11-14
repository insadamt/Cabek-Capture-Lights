# Standalone lighting service deployment

This guide deploys the lighting API from **cabek-esp32** independently of CABEK AI.
It depends on Python, FastAPI, pyserial, systemd and the existing ESP32 firmware.
The application publishes lifecycle snapshots to this service; AutoEstimate is unchanged.

## Lighting server (port 8001)

1. Install this repository under `/opt/cabek-esp32`. Create its Python virtual
   environment and install `requirements-lighting.txt`.
2. Copy `.env.example` to `/etc/cabek-lighting.env` with root ownership and mode
   0600. Set `CABEK_LIGHTS_ENABLED=1`, the verified ESP32 by-id port and distinct
   control/maintenance tokens of at least 32 characters. Use `dmx_rgb` for physical
   hardware; `simulated_pixels` opens no serial port.
3. Give the `cabek` service account the actual serial device's group access
   (`dialout` on many Ubuntu installs). Close serial monitors and other USB owners.
4. Review paths/account in `deploy/cabek-lighting.service`, then install it:

```sh
sudo install -m 0644 deploy/cabek-lighting.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cabek-lighting
journalctl -u cabek-lighting -f
```

For development use `.env` in this repository and `python -m lighting_api --port 8001`.
Only one process may own the serial port. Never run a second embedded USB bridge.
Firmware and wiring remain unchanged by the service relocation. New smooth RGB
requires `protocol=rgb8-v1`; use the firmware migration checklist before uploading.
This task does not install services or upload/reset hardware.

## CABEK application (separate process, normally port 8000)

Keep model, capture and storage configuration in the existing application environment.
Replace its serial/driver/maintenance configuration with the HTTP client settings:

```ini
CABEK_LIGHTS_ENABLED=1
CABEK_LIGHTS_API_URL=http://127.0.0.1:8001
CABEK_LIGHTS_TOKEN=<same-control-token-as-lighting-service>
CABEK_LIGHTS_TIMEOUT=1
CABEK_LIGHTS_HEALTH_SECONDS=5
```

Start CABEK AI as usual (`python -m api --port 8000`). Its readiness checks and
capture hooks publish authenticated state snapshots on one bounded HTTP worker.
Unavailable lighting cannot block capture requests. Snapshots retry with the latest
state, active capture identity and elapsed phase; obsolete events are not queued.
Start/restart the lighting service independently: CABEK's next heartbeat resynchronizes
it. A client process shutdown sends OFF best effort. If the client is killed or the
network is unavailable, the service retains the last state until a new snapshot.

`deploy/cabek-tunnel.service` remains an application unit example; it no longer
owns serial or the lighting API. Keep both services on the trusted local machine.

## Frontend

Set `VITE_LIGHTS_API_BASE_URL=http://127.0.0.1:8001` independently of
`VITE_API_BASE_URL`. In development, `/api/v1/lights` is proxied to the lighting
server before other `/api` paths are proxied to CABEK. In production, configure the
actual lighting URL and `CABEK_LIGHTS_CORS_ORIGINS` with the frontend origin, or route
that prefix to port 8001 through the existing authenticated gateway. A remote
browser's `127.0.0.1` is its own machine: set the real gateway URL for remote access.

Open `/maintenance/lights` and enter the maintenance token manually. Never place
tokens in Vite environment variables or browser storage. Ordinary users do not
receive maintenance credentials. Protect all existing capture routes separately.

## Manual checks

- [ ] Start the lighting API independently and inspect authenticated `/status`,
  `/capabilities` and `/effects` on port 8001. CABEK's port must return no lighting routes.
- [ ] Start CABEK AI; observe boot/initialization/readiness and actual capture
  events arriving through `/events`. Refreshing the frontend must not replay boot.
- [ ] Preview effects from the maintenance panel. Start a scan and verify it
  cancels previews; completion holds green for ten seconds, then returns to white.
- [ ] Stop/restart either service; verify latest-state/phase recovery without
  duplicate timers or serial owners. Stop CABEK normally and verify best-effort OFF.
- [ ] Test missing/bad credentials, capability restrictions, USB reconnection and
  M–P simulation. Observe real colors/smoothness and run the full hardware soak.

See [the API contract](lighting-api.md) and [firmware/effect checklist](lighting-effects.md).
