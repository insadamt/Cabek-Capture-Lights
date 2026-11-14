# Deployment

The lighting API runs on the tunnel PC, separately from CABEK AI. The default address is:

```text
http://127.0.0.1:8001
```

The server has no authentication and is intentionally bound to **localhost**. Do not publish these controls directly on a LAN or the Internet.

## Local development

Follow the [Quick start](../README.md) and set `CABEK_LIGHTS_PORT` to the ESP32 serial device.

To discover a stable port on Linux:

```bash
ls -l /dev/serial/by-id/
```

Using `auto` is supported only when exactly one device appears under that directory. The user running the service must have access to the serial device, typically through the `dialout` group.

Start the service:

```bash
.venv/bin/python -m lighting_api --port 8001
```

Use one process, without auto-reload or multiple workers. Close Serial Monitor while it is running.

## Ubuntu / systemd

The bundled unit assumes a `cabek` user and a checkout at `/opt/cabek-esp32`. Change those paths if your setup differs.

```bash
sudo install -o root -g root -m 0600 .env.example /etc/cabek-lighting.env
sudoedit /etc/cabek-lighting.env
# Set CABEK_LIGHTS_PORT, save the file, then continue.
sudo install -m 0644 deploy/cabek-lighting.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cabek-lighting
sudo systemctl status cabek-lighting
```

The systemd unit loads `/etc/cabek-lighting.env`; the development command loads the repository's local `.env`.

Follow logs with:

```bash
journalctl -u cabek-lighting -f
```

## Configuration

Settings come from the environment or the local `.env` file.

| Variable | Default | Purpose |
|---|---|---|
| `CABEK_LIGHTS_PORT` | `auto` | USB serial device |
| `CABEK_LIGHTS_BAUD` | `115200` | ESP32 console baud rate |
| `CABEK_LIGHTS_TIMEOUT` | `1` | Serial command timeout (seconds) |
| `CABEK_LIGHTS_RECONNECT_SECONDS` | `2` | Retry interval |
| `CABEK_LIGHTS_HEALTH_SECONDS` | `5` | Idle serial health interval |
| `CABEK_LIGHTS_UPDATE_HZ` | `15` | Animation update rate, maximum 20 |

## CABEK AI integration

Set these values in the **CABEK AI backend**:

```env
CABEK_LIGHTS_ENABLED=1
CABEK_LIGHTS_API_URL=http://127.0.0.1:8001
```

CABEK AI decides when to send startup, scan, completion or shutdown commands. It also manages the ten-second return to white after a successful scan.

The central settings page in CABEK AI forwards manual light tests through its backend. The browser does not need a direct lighting-service URL.

## Troubleshooting

| Symptom | Check |
|---|---|
| USB port not found | `CABEK_LIGHTS_PORT` and `/dev/serial/by-id/` |
| Permission denied | Serial device group and service user |
| Device busy | Another service or Serial Monitor using the port |
| `501` for effects | Firmware lacks `rgb8-v1` |
| `503` on commands | Serial connection, cable or device response |
| Colors work but animations do not | Firmware version and RGB command support |

After deployment, run the [hardware checklist](hardware.md). A successful HTTP response alone does not confirm visible LED output.
