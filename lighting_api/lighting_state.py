"""Own tunnel lighting transitions, capture priority, and cancellable deadlines.

Depends on a monotonic clock and the capture service's real lifecycle events;
HTTP handlers and the serial worker share this small synchronized state machine.
"""

from datetime import datetime, timezone
from threading import RLock
import time

from lighting_api.errors import DossierError
from lighting_api.lighting_protocol import COLORS


STATES = ("BOOTING", "INITIALIZING", "READY", "SCANNING", "COMPLETED", "OFF")
STATE_COLORS = dict(zip(STATES, ("BLUE", "BLUE", "WHITE", "RED", "GREEN", "OFF")))
TRANSITIONS = {
    "BOOTING": {"INITIALIZING", "OFF"},
    "INITIALIZING": {"READY", "OFF"},
    "READY": {"SCANNING", "INITIALIZING", "OFF"},
    "SCANNING": {"COMPLETED", "READY", "INITIALIZING", "OFF"},
    "COMPLETED": {"SCANNING", "READY", "INITIALIZING", "OFF"},
    "OFF": {"BOOTING", "INITIALIZING", "READY"},
}


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class LightingState:
    def __init__(self, clock=time.monotonic):
        self.lock = RLock()
        self.clock = clock
        self.state = "OFF"
        self.revision = 0
        self.warning = False
        self.transitioned_at = timestamp()
        self.entered_at = clock()
        self.ready = False
        self.readiness_error = "Application initialization has not completed."
        self.capture_id = None
        self.completion_deadline = None
        self.test_color = None
        self.test_deadline = None

    def transition(self, state):
        if state == self.state:
            return
        if state not in TRANSITIONS[self.state]:
            raise DossierError(409, "lighting_transition_conflict", "Invalid lighting transition.")
        self.state = state
        self.revision += 1
        self.warning = False
        self.entered_at = self.clock()
        self.transitioned_at = timestamp()
        self.completion_deadline = self.clock() + 10 if state == "COMPLETED" else None
        self.test_color = self.test_deadline = None

    def set_readiness(self, error):
        with self.lock:
            self.ready = error is None
            self.readiness_error = error
            if self.capture_id or self.state in ("BOOTING", "OFF"):
                return
            if not self.ready:
                self.transition("INITIALIZING")
            elif self.state == "INITIALIZING":
                self.transition("READY")

    def request_state(self, state):
        with self.lock:
            if self.capture_id:
                if state == "SCANNING":
                    return
                raise DossierError(409, "lighting_capture_active", "Capture owns the tunnel lights.")
            if state in ("SCANNING", "COMPLETED") and state != self.state:
                raise DossierError(409, "lighting_capture_required", "Only actual capture events can enter this state.")
            if state == "READY" and not self.ready:
                raise DossierError(409, "lighting_not_ready", "Required application services are unavailable.")
            if state == self.state and self.warning:
                self.warning = False
                self.revision += 1
            self.transition(state)

    def begin_capture(self, capture_id):
        with self.lock:
            if self.capture_id == capture_id:
                return
            if self.capture_id:
                raise DossierError(409, "lighting_capture_active", "Another capture owns the tunnel lights.")

            # Capture admission is authoritative even during startup or maintenance.

            self.capture_id = capture_id
            if self.state in ("OFF", "BOOTING", "INITIALIZING"):
                self.state = "READY"
            self.transition("SCANNING")

    def finish_capture(self, capture_id, successful):
        with self.lock:
            if self.capture_id != capture_id:
                return
            self.capture_id = None
            self.transition("COMPLETED" if successful else ("READY" if self.ready else "INITIALIZING"))
            self.warning = not successful

    def start_test(self, color):
        with self.lock:
            if self.capture_id or self.state != "READY" or not self.ready:
                raise DossierError(409, "lighting_test_conflict", "Maintenance testing requires an idle ready tunnel.")
            self.revision += 1
            self.test_color = color
            self.test_deadline = self.clock() + 3

    def desired_color(self):
        with self.lock:
            now = self.clock()
            if self.completion_deadline is not None and now >= self.completion_deadline:
                self.transition("READY" if self.ready else "INITIALIZING")
            if self.test_deadline is not None and now >= self.test_deadline:
                self.test_color = self.test_deadline = None
            if self.test_color:
                return self.test_color
            if self.state == "BOOTING":
                return "BLUE" if int((now - self.entered_at) / 0.5) % 2 == 0 else "OFF"
            return STATE_COLORS[self.state]

    def snapshot(self):
        with self.lock:
            color = self.desired_color()
            return {"revision": self.revision, "warning": self.warning, "state": self.state, "color": color, "rgb": COLORS[color][1],
                    "ready": self.ready, "readiness_error": self.readiness_error,
                    "active_capture_id": self.capture_id, "test_active": self.test_color is not None,
                    "last_transition_at": self.transitioned_at}
