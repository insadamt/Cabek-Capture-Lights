# Tunnel lighting deployment

This guide installs automatic backend-owned ESP32 lighting on the Linux tunnel PC.
It depends on the sibling `cabek_ai_global` FastAPI application, its documented
capture provider, pyserial, systemd and compatible `cabek-dmx-v1` firmware. See [effects and firmware migration](lighting-effects.md).

## Architecture and compatibility

React's existing capture request → FastAPI CaptureService → single persistent
serial worker → ESP32 → UART2/MAX485 → DMX decoder → RGB strips.
The backend owns startup, capture, completion and maintenance arbitration. It
reuses the production console protocol. Smooth effects require the negotiated
`rgb8-v1` extension; legacy firmware retains fixed-color lifecycle behavior.
GPIO wiring, 250000-baud 8N2 DMX, address 001, and RGB channels 1–3 are unchanged.
White uses RGB 255/255/255; the disconnected W wire stays disconnected.

The complete API, state rules, readiness checks, environment variables, safe
failure behavior and curl examples are in
[the backend lighting contract](../../cabek_ai_global/docs/lighting-api.md).
The existing serial diagnostics remain in [the technical journal](technical-journal.md).

## Configure the host

1. Install the backend at `/opt/cabek-ai` with its Python virtual environment,
   `requirements-api.txt` and `requirements-scan.txt`, and the existing model
   files. Keep sample photographs and writable dossiers under `/var/lib/cabek-ai`.
   The example assumes a service account named `cabek`, with access to this
   directory. Adapt installation paths/user in the unit when needed.
2. Inspect `ls -l /dev/serial/by-id/` and use the actual ESP32 symlink. Do not
   copy a machine-specific ttyUSB number. Auto detection intentionally refuses
   zero or multiple by-id devices to avoid writing to an unrelated serial device.
3. Give the service account serial access. Ubuntu commonly uses the `dialout`
   group; Arch commonly uses `uucp`. Inspect the actual device group first:
   `stat -Lc '%n %G %a' /dev/serial/by-id/<actual-ESP32-device>`. Add `cabek` to
   that group and restart the service after the group change. Avoid world-writable
   serial device permissions. Close all serial monitors/diagnostic testers.
4. Create `/etc/cabek-ai.env` (root-owned, mode 0600). Systemd reads it before
   dropping privileges. Set the existing model/capture/pricing configuration and
   the lighting settings below. Generate separate random credentials of at least
   32 characters; never copy credentials into frontend environment variables.

```ini
CABEK_DOSSIERS_DIR=/var/lib/cabek-ai/dossiers
CABEK_MODELS_DIR=/opt/cabek-ai/models
CABEK_TUNNEL_MODE=mock
CABEK_MOCK_PHOTOS_DIR=/var/lib/cabek-ai/tunnel-photos
CABEK_LIGHTS_ENABLED=1
CABEK_LIGHTS_PORT=/dev/serial/by-id/<actual-ESP32-device>
CABEK_LIGHTS_BAUD=115200
CABEK_LIGHTS_TOKEN=<independent-control-secret>
CABEK_LIGHTS_MAINTENANCE_TOKEN=<independent-maintenance-secret>
CABEK_LIGHTS_TIMEOUT=1
CABEK_LIGHTS_RECONNECT_SECONDS=2
CABEK_LIGHTS_HEALTH_SECONDS=5
CABEK_LIGHTS_DRIVER=dmx_rgb
CABEK_LIGHTS_UPDATE_HZ=15
CABEK_LIGHTS_PREVIEW_SECONDS=30
CABEK_LIGHTS_BRIGHTNESS_LIMIT=100
```

Current application capture is still the existing mock photo provider; this
installation does not add camera drivers. A missing/invalid provider, model
backend, supervisor or writable storage prevents READY. Pricing/API credentials
and CORS remain the backend's existing configuration. Lighting hardware failure
is reported separately and does not block HTTP/capture work.

## Install automatic startup

Review/adapt the supplied unit, then run on the tunnel host:

```sh
sudo install -m 0644 deploy/cabek-tunnel.service /etc/systemd/system/cabek-tunnel.service
sudo systemctl daemon-reload
sudo systemctl enable --now cabek-tunnel.service
systemctl status cabek-tunnel.service
journalctl -u cabek-tunnel.service -f
```

This launches `python -m api --port 8000`, binding only to `127.0.0.1`.
BOOTING starts in the Python launcher; lifespan moves to INITIALIZING. Readiness
checks drive READY without an arbitrary startup delay. The serial owner starts
and stops with the backend. Use one process and no Uvicorn reload/multiple workers.
Do not also start a second standalone bridge or PlatformIO monitor.

The unit is an installation example; the repository task does not install/enable
it on this development machine. It requires the configured deployment paths,
service account and device permissions. `ProtectHome=true` assumes installation
under `/opt`; adjust the unit if intentionally deploying elsewhere.

Keep the whole capture API behind the existing trusted local boundary. Lighting
endpoints require bearer credentials, and maintenance testing needs its own
credential. Any remote gateway must authenticate **all** capture and lighting
routes; CORS is not access control. The frontend does not receive serial secrets.

## Failure and recovery checks

USB disconnect clears current acknowledgment and triggers bounded-timeout retries
with backoff. The current desired state is reapplied after firmware validation on
reconnection. Device restarts/status regressions also trigger reconnect. Status
separates desired RGB, historical firmware/last command and current connection;
serial acknowledgment does not establish visible LED color.

With RGB-capable firmware, Target Lock and red pulses replace fixed red;
failed captures use amber warning and graceful shutdown fades through dim blue.
Legacy firmware retains the original fixed colors. Capture owns lighting until all required originals are saved and validated. Failure
or shutdown interruption never enters green. Completion holds green for 10 seconds
and returns to white only if application health still permits READY. A new capture
cancels that timer. Graceful service shutdown attempts OFF. An unplugged ESP32 or
forced kill may leave the previous output; this firmware has no host-loss watchdog.

After recovery inspect `last_error`, `last_seen_at`, `connection_status` and
`synchronized` through the authenticated status endpoint. Increasing DMX frame
counters and zero errors are checked by periodic firmware status queries.

## Manual acceptance checklist

- [ ] Check the ESP32 device identity and permissions; enable/restart the service
  on the tunnel PC and confirm it starts automatically after a host reboot.
- [ ] Observe blue awakening (legacy blink) while booting, blue breathing (legacy
  solid blue) during initialization and white only after actual readiness passes. Very fast startup
  may make BOOTING brief; do not insert a fake delay to make it visible.
- [ ] Remove a required dependency/sample/storage permission and verify the state
  remains INITIALIZING; repair it and confirm automatic readiness recovery.
- [ ] In idle READY, use the maintenance API for RED/BLUE/GREEN/WHITE/OFF and the protected effects panel. Observe
  the actual strips and RGB white; verify automatic restoration after 3 seconds.
- [ ] Start capture from React. Confirm Target Lock/red pulses (legacy red) during photo delivery, green only on
  successful photo completion, then white after 10 seconds. Navigation/refresh
  must not restart BOOTING or extend completion.
- [ ] Begin another capture during green; confirm red persists beyond the old
  timer. Repeat/concurrently submit capture and lighting requests and inspect
  conflict responses, with no interrupted capture or duplicate success events.
- [ ] Fail/interrupt a capture or stop the application while capturing; verify no
  green, retained photo evidence and safe recovery after restart.
- [ ] Disconnect/reconnect USB while idle and during capture, then reset ESP32.
  Verify status loss, bounded retries, stable by-id lookup and current-state replay.
- [ ] Start with ESP32 absent; verify normal application operation and honest
  unavailable/unsynchronized hardware status. Connect it and confirm recovery.
- [ ] Verify missing/bad credentials return 401, control credentials cannot test
  (403), maintenance tests conflict during capture (409), and malformed inputs
  return 422. Verify deployment does not expose unauthenticated capture routes.
- [ ] Stop the systemd service normally and observe OFF. Run a longer hardware
  soak for readable serial status, increasing DMX frames and zero errors.

Use the [advanced effect acceptance checklist](lighting-effects.md) for all effects,
capability restrictions and simulation.

Physical LED appearance, real USB removal, power resets and installed systemd
startup require observation on the actual tunnel hardware.
