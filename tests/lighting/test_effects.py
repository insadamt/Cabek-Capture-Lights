"""Verify every global effect, validation, palettes, timing and final colors.

Depends only on pure rendering and Pydantic; no hardware or wall-clock timing.
"""
import pytest
from pydantic import ValidationError

from lighting_api.lighting_effects import EffectRequest, GLOBAL_EFFECTS, easing, render_effect


def test_defaults_brightness_and_relevant_parameter_validation():
    assert EffectRequest().effect == 'solid'
    assert render_effect(EffectRequest(), 999).output_rgb == (255, 255, 255)
    assert render_effect(EffectRequest(color='#FF8000', brightness=50), 0).output_rgb == (128, 64, 0)
    assert render_effect(EffectRequest(brightness=0), 0).output_rgb == (0, 0, 0)
    request = EffectRequest(effect='solid', speed='ignored', duration_ms=-1, repeat='ignored',
                            colors=[None], easing='ignored')
    assert request.speed == 1 and request.duration_ms == 2000
    assert EffectRequest(effect='warning', color='ignored').color == '#FFFFFF'
    assert EffectRequest(effect='color_cycle', color='ignored', colors=['#FF0000', '#0000FF']).color == '#FFFFFF'


@pytest.mark.parametrize('payload', [dict(effect='missing'), dict(brightness=101), dict(brightness=True),
    dict(color='red'), dict(effect='fade_in', duration_ms=True), dict(effect='fade_in', duration_ms=0),
    dict(effect='pulse', speed=0), dict(effect='pulse', speed=5.1), dict(effect='pulse', repeat='true'),
    dict(effect='pulse', brightness=float('nan')), dict(effect='pulse', speed=float('inf')),
    dict(effect='fade_in', easing='missing'), dict(effect='color_cycle'),
    dict(effect='color_cycle', colors=['#000000']), dict(effect='transition', colors=['bad', '#FFFFFF']),
    dict(effect='transition', colors=['#000000', 42]), dict(pixel_count=10)])
def test_invalid_relevant_parameters(payload):
    with pytest.raises(ValidationError):
        EffectRequest(**payload)


@pytest.mark.parametrize('name', GLOBAL_EFFECTS)
def test_every_effect_is_deterministic_finite_and_repeatable(name):
    options = {'colors': ['#0066FF', '#8B00FF', '#00FFFF']} if name == 'color_cycle' else {}
    finite = EffectRequest(effect=name, duration_ms=2000, **options)
    final = render_effect(finite, 2)
    assert final.done and render_effect(finite, 999) == final
    for elapsed in (0, .1, .5, 1, 2):
        frame = render_effect(finite, elapsed)
        assert frame == render_effect(finite, elapsed)
        assert all(0 <= value <= 255 for value in frame.output_rgb)
    if name != 'solid':
        repeating = EffectRequest(effect=name, repeat=True, duration_ms=2000, **options)
        assert not render_effect(repeating, 200).done
        assert render_effect(repeating, .5).output_rgb == render_effect(repeating, 200.5).output_rgb


@pytest.mark.parametrize('name', GLOBAL_EFFECTS[1:])
def test_speed_multiplies_playback_rate_for_every_animation(name):
    options = {'colors': ['#FF0000', '#0000FF']} if name == 'color_cycle' else {}
    normal = EffectRequest(effect=name, duration_ms=2000, **options)
    faster = EffectRequest(effect=name, duration_ms=2000, speed=2, **options)
    assert render_effect(normal, .7) == render_effect(faster, .35)
    assert render_effect(faster, 1).done
    assert not render_effect(faster, .99).done


def test_easing_and_color_arrays():
    for name in ('linear', 'ease_in', 'ease_out', 'ease_in_out'):
        values = [easing(index / 20, name) for index in range(21)]
        assert values[0] == 0 and values[-1] == 1 and values == sorted(values)
    assert easing(.25, 'ease_in') < easing(.25, 'linear') < easing(.25, 'ease_out')
    transition = EffectRequest(effect='transition', colors=['#FF0000', '#00FF00', '#0000FF'])
    assert render_effect(transition, 1).output_rgb == (0, 255, 0)
    assert render_effect(transition, 2).output_rgb == (0, 0, 255)
    cycle = EffectRequest(effect='color_cycle', colors=['#FF0000', '#0000FF'])
    assert render_effect(cycle, 1).output_rgb == (0, 0, 255)
    assert render_effect(cycle, 2).output_rgb == (255, 0, 0)
    from_current = EffectRequest(effect='transition', color='#FF0000')
    assert render_effect(from_current, 1, (0, 0, 255)).output_rgb == (128, 0, 128)


@pytest.mark.parametrize('name, expected', [('system_awakening', (0, 60, 255)),
    ('target_lock', (255, 0, 0)), ('mission_complete', (0, 255, 0)), ('shutdown', (0, 0, 0)),
    ('fade_in', (255, 255, 255)), ('fade_out', (0, 0, 0)), ('breathing', (0, 0, 0)),
    ('pulse', (0, 0, 0)), ('warning', (0, 0, 0))])
def test_choreography_final_colors(name, expected):
    assert render_effect(EffectRequest(effect=name), 2).output_rgb == expected
