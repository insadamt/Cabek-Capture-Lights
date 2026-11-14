"""Verify effect endpoints and arbitration with mock time and no physical lights.

Depends on pure renderers and the explicit simulated driver. Assertions cover
observable frames, final states, races and capability enforcement.
"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from lighting_api.errors import DossierError
from lighting_api.lighting_config import LightingSettings
from lighting_api.lighting_effects import EffectRequest, GLOBAL_EFFECTS, PIXEL_EFFECTS, easing, interpolate, render_effect
from lighting_api.lighting_service import LightingService


def simulated_service(**options):
    now = [0.0]
    settings = LightingSettings(driver='simulated_pixels', enabled=True, pixel_count=12, **options)
    service = LightingService(settings, clock=lambda: now[0])
    service.state.transition('INITIALIZING')
    service.state.set_readiness(None)
    service.synchronize()
    return service, now


def test_interpolation_easing_and_brightness_endpoints():
    assert interpolate((0, 0, 255), (255, 128, 0), .5) == (128, 64, 128)
    assert interpolate((0, 0, 0), (255, 255, 255), 10) == (255, 255, 255)
    for name in ('linear', 'ease_in', 'ease_out', 'ease_in_out'):
        values = [easing(index / 20, name) for index in range(21)]
        assert values[0] == 0 and values[-1] == 1
        assert values == sorted(values)
    assert easing(.25, 'ease_in') < easing(.25, 'linear') < easing(.25, 'ease_out')
    assert render_effect(EffectRequest(effect='solid', color='#FF8000', brightness=50), 0).output_rgb == (128, 64, 0)


@pytest.mark.parametrize('name', GLOBAL_EFFECTS)
def test_all_global_effects_are_bounded_and_deterministic(name):
    request = EffectRequest(effect=name)
    for elapsed in (0, .1, .5, 1, 2, 5, 120):
        frame = render_effect(request, elapsed)
        assert frame == render_effect(request, elapsed)
        assert all(0 <= value <= 255 for value in frame.output_rgb)
        assert 0 <= frame.brightness <= 100
        assert frame.pixels is None


def test_fade_breathing_pulse_and_color_transition_semantics():
    fade = EffectRequest(effect='fade_in', color='#FFFFFF', brightness=100, duration_ms=1000)
    assert [render_effect(fade, point).output_rgb for point in (0, .5, 1)] == [(0, 0, 0), (128, 128, 128), (255, 255, 255)]
    assert render_effect(EffectRequest(effect='fade_out'), 2).output_rgb == (0, 0, 0)
    breath = EffectRequest(effect='breathing', min_brightness=10, brightness=90, duration_ms=1000, repeat=True)
    assert [render_effect(breath, point).brightness for point in (0, .5, 1)] == [10, 90, 10]
    pulse = EffectRequest(effect='pulse', color='#FF0000', brightness=100, count=1)
    assert render_effect(pulse, .25).output_rgb == (255, 0, 0)
    assert render_effect(pulse, 1).done and render_effect(pulse, 1).output_rgb == (0, 0, 0)
    transition = EffectRequest(effect='transition', from_color='#0000FF', color='#FF0000', brightness=100)
    assert render_effect(transition, 1).output_rgb == (128, 0, 128)


def test_named_sequences_finish_with_the_required_output():
    for name, expected in [('system_awakening', (0, 60, 255)), ('target_lock', (255, 0, 0)),
                           ('mission_complete', (0, 255, 0)), ('shutdown', (0, 0, 0))]:
        frame = render_effect(EffectRequest(effect=name, brightness=100), 2)
        assert frame.done and frame.output_rgb == expected
    assert render_effect(EffectRequest(effect='system_awakening'), 0).output_rgb == (0, 0, 0)
    assert render_effect(EffectRequest(effect='warning', brightness=0), 0).output_rgb == (0, 0, 0)


@pytest.mark.parametrize('payload', [dict(effect='missing'), dict(effect='solid', brightness=101),
    dict(effect='breathing', min_brightness=90, brightness=80), dict(effect='solid', color='red'),
    dict(effect='solid', duration_ms=10), dict(effect='chase', speed=0), dict(effect='fade_in', duration_ms=True),
    dict(effect='solid', repeat='true'), dict(effect='pulse', count=0), dict(effect='fade_in', duration_ms=120001)])
def test_invalid_or_irrelevant_parameters_are_rejected(payload):
    with pytest.raises(ValidationError):
        EffectRequest(**payload)


@pytest.mark.parametrize('name', PIXEL_EFFECTS)
def test_zone_effects_only_render_with_explicit_zone_count(name):
    request = EffectRequest(effect=name, brightness=100)
    with pytest.raises(ValueError):
        render_effect(request, 0)
    frame = render_effect(request, 1, 12)
    assert len(frame.pixels) == 12
    assert all(0 <= channel <= 255 for pixel in frame.pixels for channel in pixel)
    reverse = request.model_copy(update={'direction': 'reverse'})
    assert render_effect(reverse, 1, 12).pixels == frame.pixels[::-1]


def test_progressive_reveal_and_scanner_have_spatial_behavior():
    request = EffectRequest(effect='progressive_reveal', color='#FF0000', brightness=100, duration_ms=1000)
    assert sum(any(pixel) for pixel in render_effect(request, .5, 12).pixels) == 6
    assert all(pixel == (255, 0, 0) for pixel in render_effect(request, 1, 12).pixels)
    scanner = EffectRequest(effect='scanner_sweep', segment_length=1, speed=2, repeat=True)
    assert render_effect(scanner, 0, 5).pixels == render_effect(scanner, 4, 5).pixels
    assert render_effect(scanner, 0, 5).pixels == render_effect(scanner, 2, 5).pixels[::-1]


def test_preview_idempotency_replacement_expiry_and_scan_priority():
    service, now = simulated_service(preview_seconds=30)
    caps = service.driver.get_capabilities()
    request = EffectRequest(effect='breathing', repeat=True)
    service.engine.start_preview(request, caps)
    service.status()
    now[0] = 1
    start = service.engine.started
    service.engine.start_preview(request, caps)
    assert service.engine.started == start
    assert service.engine.preview_deadline == 30
    service.engine.start_preview(EffectRequest(effect='solid', color='#00FF00'), caps)
    assert service.status()['active_effect'] == 'solid'
    service.engine.stop_preview()
    assert service.status()['active_effect'] == 'transition'
    service.engine.start_preview(request, caps)
    now[0] = 31
    assert not service.status()['preview_active']
    service.engine.start_preview(request, caps)
    service.state.begin_capture('new')
    assert not service.status()['preview_active']
    for action in (lambda: service.engine.start_preview(request, caps), service.engine.stop_preview):
        with pytest.raises(DossierError) as raised:
            action()
        assert raised.value.status_code == 409


def test_lifecycle_completion_deadline_and_new_capture_cancel_old_effect():
    service, now = simulated_service()
    assert service.status()['active_effect'] == 'transition'
    service.state.begin_capture('first')
    assert service.status()['active_effect'] == 'target_lock'
    now[0] = 1.3
    assert service.status()['active_effect'] == 'pulse'
    service.state.finish_capture('first', True)
    assert service.status()['active_effect'] == 'mission_complete'
    now[0] = 11.3
    assert service.status()['state'] == 'READY'
    now[0] = 12.2
    assert service.status()['rgb'] == (255, 255, 255)
    service.state.begin_capture('second')
    service.state.finish_capture('second', True)
    now[0] = 15
    service.state.begin_capture('third')
    now[0] = 30
    assert service.status()['state'] == 'SCANNING'
    assert service.state.completion_deadline is None
    service.state.finish_capture('third', False)
    assert service.status()['active_effect'] == 'warning'
    service.state.request_state('READY')
    assert service.status()['active_effect'] == 'transition'


def test_concurrent_preview_requests_use_one_owner_and_cannot_interrupt_capture():
    service, _ = simulated_service()
    caps = service.driver.get_capabilities()
    def preview(index):
        service.engine.start_preview(EffectRequest(effect='solid', brightness=float(index)), caps)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(preview, range(100)))
    assert service.thread is None
    service.state.begin_capture('scan')
    assert not service.status()['preview_active']
    assert service.engine.preview is None


def test_simulation_mapping_and_brightness_limit_do_not_claim_physical_leds():
    service, now = simulated_service(brightness_limit=50, color_order='GRB', pixel_mapping=tuple(reversed(range(12))))
    service.engine.start_preview(EffectRequest(effect='progressive_reveal', color='#FF0000', brightness=100, duration_ms=1000), service.driver.get_capabilities())
    service.synchronize()
    now[0] = .5
    service.synchronize()
    assert service.driver.logical_pixels[:6] == tuple([(128, 0, 0)] * 6)
    assert service.driver.physical_pixels[6:] == tuple([(0, 128, 0)] * 6)
    status = service.status()
    assert status['simulated'] and not status['esp32_available']
    assert status['synchronized']


def test_initial_off_does_not_flash_white_and_shutdown_finishes_off():
    service, now = simulated_service()
    now[0] = 1
    assert service.status()['rgb'] == (255, 255, 255)
    service.state.request_state('OFF')
    assert service.status()['active_effect'] == 'shutdown'
    now[0] = 2
    assert service.status()['rgb'] == (0, 0, 0)
    assert service.state.state == 'OFF'


def test_zone_to_global_switch_keeps_historical_confirmation_type_valid():
    from lighting_api.lighting_schemas import LightingStatus
    service, now = simulated_service()
    caps = service.driver.get_capabilities()
    service.engine.start_preview(EffectRequest(effect='chase', repeat=True), caps)
    now[0] = .1
    service.synchronize()
    service.engine.start_preview(EffectRequest(effect='solid'), caps)
    result = LightingStatus.model_validate(service.status())
    assert result.acknowledged_rgb is None
    assert not result.synchronized
    now[0] = .2
    service.synchronize()
    assert service.status()['synchronized']
    service.state.start_test('RED')
    service.engine.settings = LightingSettings(brightness_limit=50)
    assert service.status()['rgb'] == (128, 0, 0)
