# Local deployment

Run the independent lighting service on the tunnel PC, bound to `127.0.0.1:8001`.
Depends on the Python environment, USB permissions and a trusted local caller.
CABEK AI runs separately and has no ownership of USB.

Follow the [README setup](../README.md), then set `CABEK_LIGHTS_PORT` in `.env`
to a stable `/dev/serial/by-id/...` path. `auto` requires exactly one such device.
Grant the service user access to the device group, usually `dialout`.
Use one process, without reload or multiple workers. Never run Serial Monitor
against the same device. Existing obsolete environment options are ignored.

For systemd, adapt `deploy/cabek-lighting.service` to your user and repository:

```sh
sudo install -o root -g root -m 0600 .env.example /etc/cabek-lighting.env
# Configure the stable USB device in /etc/cabek-lighting.env.
sudo install -m 0644 deploy/cabek-lighting.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cabek-lighting
journalctl -u cabek-lighting -f
```

`CABEK_LIGHTS_TIMEOUT` bounds serial transactions; reconnection and idle health
intervals default to 2 and 5 seconds. `CABEK_LIGHTS_UPDATE_HZ` defaults to 15
(maximum 20), with identical RGB frames suppressed. No hardware is opened until
a command arrives. Later serial failures are visible in service logs.

## CABEK AI and browser integration

In the CABEK AI server environment:

```ini
CABEK_LIGHTS_ENABLED=1
CABEK_LIGHTS_API_URL=http://127.0.0.1:8001
```

The application sends startup `system_awakening`, solid white after its startup,
red repeating pulses during capture, `mission_complete` on success and white ten
seconds later. Failure selects `warning`, shutdown sends bodyless OFF. The client
owns the completion timer, cancels it for a new capture, and retries failed HTTP
commands outside capture requests. Accepted effects are not resent as heartbeats.
No lighting readiness probe or application snapshot is required by the API.

All application lighting decisions and HTTP calls run in the CABEK AI backend.
The frontend sends only its usual capture requests, with no lighting page, client,
service URL, timer or Vite lighting proxy. Configure the service URL exclusively
through the backend's `CABEK_LIGHTS_API_URL`. CABEK AI does not expose lighting
endpoints to the browser. Keep the independent service on loopback; use its two
HTTP endpoints locally for manual diagnostics.

Use the [manual hardware checklist](lighting-effects.md) before accepting the
installation. Do not claim visible LED behavior from serial acknowledgments alone.
