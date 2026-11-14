"""Exercise cancellation, single-worker ownership and recovery deterministically.

Depends on fake firmware, controlled clocks and events; no physical hardware.
"""
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event, Thread, get_ident

import pytest

from firmware_fake import FirmwareSerial
from lighting_api.errors import LightingError
from lighting_api.lighting_config import LightingSettings
from lighting_api.lighting_effects import EffectRequest
from lighting_api.lighting_protocol import SerialLightingLink
from lighting_api.lighting_service import LightingService, PendingCommand


def make_service():
    now = [0.0]
    ports = []
    settings = LightingSettings(port='fake', timeout=.01)
    def factory(**kwargs):
        port = FirmwareSerial(**kwargs)
        ports.append(port)
        return port
    service = LightingService(settings, SerialLightingLink(settings, factory), lambda: now[0])
    return service, ports, now


def execute(service, request):
    service.generation += 1
    command = PendingCommand(request, service.generation, Future())
    service.execute_command(command)
    return command.result.result()


def test_finite_final_color_hold_repeat_and_deduplication():
    service, ports, now = make_service()
    try:
        execute(service, EffectRequest(effect='fade_in', color='#FF0000', duration_ms=2000, speed=2))
        now[0] = .5
        service.synchronize()
        assert ports[0].output == (128, 0, 0)
        now[0] = 1
        service.synchronize()
        assert ports[0].output == (255, 0, 0) and service.active is None
        count = len(ports[0].writes)
        for _ in range(100):
            service.synchronize()
        assert len(ports[0].writes) == count
        now[0] = 100
        service.synchronize()
        assert ports[0].output == (255, 0, 0)
        execute(service, EffectRequest(effect='breathing', repeat=True))
        now[0] = 131
        service.synchronize()
        assert service.active.repeat and ports[0].output == (255, 255, 255)
        execute(service, None)
        now[0] = 999
        service.synchronize()
        assert service.active is None and ports[0].output == (0, 0, 0)
    finally:
        service.link.close()


def test_disconnect_reconnect_replays_current_animation_frame():
    service, ports, now = make_service()
    try:
        execute(service, EffectRequest(effect='breathing', color='#FF0000', repeat=True))
        ports[0].broken = True
        now[0] = .5
        service.synchronize()
        assert service.link.port is None and service.acknowledged_output is None
        service.synchronize()
        assert len(ports) == 1
        now[0] = 3
        service.synchronize()
        assert len(ports) == 2 and ports[1].output == (255, 0, 0)
        assert service.last_error is None
        assert service.active.repeat
    finally:
        service.link.close()


def test_failed_off_cancels_animation_and_off_is_retried_after_reconnect():
    service, ports, now = make_service()
    try:
        execute(service, EffectRequest(effect='pulse', repeat=True))
        ports[0].broken = True
        service.active = None
        service.desired_output = (0, 0, 0)
        with pytest.raises(LightingError) as error:
            execute(service, None)
        assert error.value.status_code == 503
        now[0] = 2
        service.synchronize()
        assert ports[-1].output == (0, 0, 0) and service.active is None
    finally:
        service.link.close()


def test_off_preempts_queued_set_and_all_serial_updates_share_one_worker():
    service, ports, _ = make_service()
    entered, release = Event(), Event()
    writes = []
    original = service.link.send_output
    def slow_first(output):
        writes.append((get_ident(), output))
        if len(writes) == 1:
            entered.set()
            assert release.wait(2)
        original(output)
    service.link.send_output = slow_first
    service.start()
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            first = pool.submit(service.set_effect, EffectRequest(color='#FF0000'))
            assert entered.wait(1)
            # Queue SET and OFF while the first acknowledgment is in flight.

            pending = Future()
            with service.condition:
                service.generation += 1
                service.pending.append(PendingCommand(EffectRequest(color='#00FF00'), service.generation, pending))
            stopped = pool.submit(service.off)
            # Wait for OFF to enter the queue without relying on wall-clock sleeps.

            with service.condition:
                assert service.condition.wait_for(lambda: any(c.request is None for c in service.pending), timeout=1)
            release.set()
            assert first.result(timeout=1)['success']
            assert stopped.result(timeout=1)['status'] == 'off'
            with pytest.raises(LightingError) as error:
                pending.result(timeout=1)
            assert error.value.status_code == 409
        assert ports[0].output == (0, 0, 0)
        assert all(thread_id == service.thread.ident for thread_id, _ in writes)
        assert (0, 255, 0) not in [output for _, output in writes]
    finally:
        release.set()
        service.close()


def test_animation_schedules_first_frame_then_returns_before_completion():
    service, _, now = make_service()
    service.start()
    try:
        result = service.set_effect(EffectRequest(effect='fade_in', duration_ms=120000))
        assert result['status'] == 'running'
        assert now[0] == 0 and service.active.effect == 'fade_in'
        assert service.off()['status'] == 'off'
        assert service.active is None
    finally:
        service.close()
