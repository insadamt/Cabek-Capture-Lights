"""Verify deterministic deadlines, capture ownership and concurrent state requests.

Depends on a controllable monotonic clock; no wall-clock waits or LEDs are needed.
"""

from concurrent.futures import ThreadPoolExecutor

import pytest

from lighting_api.errors import DossierError
from lighting_api.lighting_state import LightingState


@pytest.fixture
def state():
    now = [0.0]
    machine = LightingState(lambda: now[0])
    machine.transition("BOOTING")
    return machine, now


def ready(machine):
    machine.transition("INITIALIZING")
    machine.set_readiness(None)


def test_startup_blink_and_readiness_gate(state):
    machine, now = state
    assert machine.desired_color() == "BLUE"
    now[0] = .5
    assert machine.desired_color() == "OFF"
    now[0] = 42
    assert machine.desired_color() == "BLUE"
    machine.transition("INITIALIZING")
    now[0] = 42.5
    assert machine.desired_color() == "BLUE"
    with pytest.raises(DossierError):
        machine.request_state("READY")
    machine.set_readiness(None)
    assert machine.desired_color() == "WHITE"
    machine.set_readiness("storage unavailable")
    assert machine.state == "INITIALIZING"


def test_complete_timer_duplicate_events_and_new_scan(state):
    machine, now = state
    ready(machine)
    machine.begin_capture("first")
    assert machine.desired_color() == "RED"
    machine.finish_capture("first", True)
    now[0] = 9
    machine.finish_capture("first", True)
    machine.request_state("COMPLETED")
    assert machine.desired_color() == "GREEN"
    now[0] = 10
    assert machine.desired_color() == "WHITE"
    machine.begin_capture("second")
    machine.finish_capture("second", True)
    now[0] = 19
    machine.begin_capture("third")
    machine.finish_capture("second", True)
    now[0] = 21
    assert machine.desired_color() == "RED"
    machine.finish_capture("third", False)
    assert machine.desired_color() == "WHITE"


def test_scan_priority_failure_and_test_expiry(state):
    machine, now = state
    ready(machine)
    machine.start_test("BLUE")
    assert machine.desired_color() == "BLUE"
    now[0] = 3
    assert machine.desired_color() == "WHITE"
    machine.start_test("GREEN")
    machine.begin_capture("scan")
    for requested in ("BOOTING", "INITIALIZING", "READY", "COMPLETED", "OFF"):
        with pytest.raises(DossierError):
            machine.request_state(requested)
    with pytest.raises(DossierError):
        machine.start_test("GREEN")
    machine.set_readiness("dependencies failed")
    assert machine.desired_color() == "RED"
    machine.finish_capture("scan", False)
    assert machine.desired_color() == "BLUE"
    assert machine.completion_deadline is None


def test_parallel_requests_cannot_replace_capture(state):
    machine, _ = state
    ready(machine)
    machine.begin_capture("scan")

    def conflicting_request(index):
        try:
            machine.request_state("READY" if index % 2 else "OFF")
        except DossierError as error:
            return error.status_code

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert list(executor.map(conflicting_request, range(100))) == [409] * 100
    assert machine.state == "SCANNING"
    assert machine.capture_id == "scan"


def test_capture_states_cannot_be_fabricated_and_off_is_sticky(state):
    machine, _ = state
    ready(machine)
    for requested in ("SCANNING", "COMPLETED", "BOOTING"):
        with pytest.raises(DossierError):
            machine.request_state(requested)
    machine.request_state("OFF")
    machine.set_readiness(None)
    assert machine.desired_color() == "OFF"
    machine.request_state("READY")
    assert machine.desired_color() == "WHITE"
