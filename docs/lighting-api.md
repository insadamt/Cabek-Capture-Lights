# Lighting API

A standalone FastAPI service running at `http://127.0.0.1:8001`. All endpoints start with `/api/v1/lights`.

CABEK AI owns the capture lifecycle; this service owns the lighting hardware. A successful API response means a request was **accepted**, not that visible LEDs were verified.

## Access

Requests do not require tokens or an Authorization header. Preview/state rules,
parameter validation and capture priority still apply.

## Endpoints

| Method | Route | Use |
| --- | --- | --- |
| GET | `/status` | State, current output and connection health |
| GET | `/capabilities` | What the connected driver can actually do |
| GET | `/effects` | Available effects and accepted parameters |
| POST | `/effects` | Start a maintenance preview |
| POST | `/stop` | Stop a preview and restore lifecycle output |
| POST | `/test` | Test a fixed color for 3 seconds |
| POST | `/state` | Request a permitted state change |
| POST | `/events` | Receive authoritative CABEK AI lifecycle snapshots |

### Try an effect

Set the base URL in your shell:

```sh
export LIGHTS=http://127.0.0.1:8001/api/v1/lights
curl "$LIGHTS/capabilities"
curl "$LIGHTS/effects"
```

When the application is healthy and **READY**, you can preview an effect:

```sh
curl -X POST "$LIGHTS/effects" -H "Content-Type: application/json" -d '{"effect":"breathing","color":"#2563EB","duration_ms":2000,"brightness":80,"repeat":true}'
```

Stop the preview:

```sh
curl -X POST "$LIGHTS/stop"
```

For a fixed three-second test, use `POST /test` with `{"color":"RED"}`. A preview/test cannot override an active scan.

### Application events

CABEK AI sends `POST /events` without credentials. Example:

```json
{
  "session_id": "app-process-uuid",
  "sequence": 12,
  "state": "SCANNING",
  "ready": true,
  "capture_id": "capture-123",
  "elapsed_ms": 1250,
  "warning": false
}
```

States: `BOOTING`, `INITIALIZING`, `READY`, `SCANNING`, `COMPLETED`, `OFF`. `capture_id` is required for SCANNING and must otherwise be absent. The application must actually be ready before reporting READY. Repeated or outdated event sequences are ignored. Only real capture events should enter SCANNING or COMPLETED; `/state` cannot fabricate them.

## Responses and errors

- `202`: accepted; the hardware may still be disconnected.
- `409`: capture conflict, invalid state transition, or unsupported effect.
- `422`: invalid request data.
- `503`: lighting service disabled.

`/status` distinguishes **requested** output from **acknowledged** output. Acknowledgment confirms serial communication, not the physical appearance of the lights. The `simulated` flag identifies memory-only output.

Use `GET /effects` for the authoritative effect names, defaults and parameter limits instead of copying stale parameter tables into client code.

See [effects](lighting-effects.md) and [deployment](lighting-deployment.md).

The lighting API listens on localhost. The development frontend lighting proxy
also accepts local requests only, even when the rest of the frontend serves the LAN.
