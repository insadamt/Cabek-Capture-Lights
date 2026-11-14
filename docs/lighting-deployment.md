# Deploy on the tunnel PC

The lighting service runs **separately** from CABEK AI on the same trusted machine:

- Lighting API: `127.0.0.1:8001`
- CABEK AI application: normally `127.0.0.1:8000`
- Only the lighting service may open the ESP32 USB serial port.

## 1. Install the lighting service

These instructions assume Ubuntu, a `cabek` service user and this repository at `/opt/cabek-esp32`:

```sh
cd /opt/cabek-esp32
python3 -m venv .venv
.venv/bin/pip install -r requirements-lighting.txt
sudo install -o root -g root -m 0600 .env.example /etc/cabek-lighting.env
```

Edit `/etc/cabek-lighting.env` and set:

- `CABEK_LIGHTS_ENABLED=1`
- `CABEK_LIGHTS_DRIVER=dmx_rgb`
- `CABEK_LIGHTS_PORT=/dev/serial/by-id/<your-device>` (list devices with `ls -l /dev/serial/by-id/`)
- Two **different** private tokens of at least 32 characters: `CABEK_LIGHTS_TOKEN` and `CABEK_LIGHTS_MAINTENANCE_TOKEN`

Grant the `cabek` user access to the actual USB serial device group (often `dialout`). Confirm that `deploy/cabek-lighting.service` matches your paths and account.

```sh
sudo install -m 0644 deploy/cabek-lighting.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cabek-lighting
sudo systemctl status cabek-lighting
```

Logs: `journalctl -u cabek-lighting -f`. Do not run PlatformIO Serial Monitor while this service owns the port. Run exactly one service process, without reload/multiple workers.

For local development, use `cp .env.example .env`, configure it, then run `.venv/bin/python -m lighting_api --port 8001`.

## 2. Connect CABEK AI

In CABEK AI's **server-side** environment, configure:

```ini
CABEK_LIGHTS_ENABLED=1
CABEK_LIGHTS_API_URL=http://127.0.0.1:8001
CABEK_LIGHTS_TOKEN=<same-control-token>
```

CABEK AI then publishes startup, readiness and capture events to `POST /api/v1/lights/events`. Lighting outages must not block vehicle capture.

For the frontend, use `VITE_LIGHTS_API_BASE_URL` pointing to the accessible lighting API or your authenticated gateway. **Never** use a remote browser's `127.0.0.1` for the tunnel PC, and never embed the maintenance token in `VITE_*` settings.

Operators can open `/maintenance/lights` and supply their maintenance token manually. Expose the API only through a trusted authenticated boundary. CORS alone is not access control.

## 3. Check the installation

1. Start the lighting service and verify authenticated `/status` and `/capabilities` on port 8001.
2. Start CABEK AI; check blue startup, white ready, red during capture, green on success, white after ten seconds.
3. Verify manual previews cannot interrupt a scan.
4. Disconnect/reconnect USB and restart either service; verify that the latest state recovers and no duplicate serial owner appears.

Do not mark an ESP32 firmware upgrade as accepted until the real decoder and lights are observed. Keep the known working firmware for rollback.

See [API examples](lighting-api.md) and [effects/hardware limits](lighting-effects.md).
