"""Validate effect requests and render deterministic global RGB animations.

Depends on Pydantic and monotonic elapsed seconds supplied by the owner; this
module performs no I/O, starts no timers, and delegates zone effects to pixels.
"""

from dataclasses import dataclass
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


RGB = tuple[int, int, int]
GLOBAL_EFFECTS = ('solid', 'fade_in', 'fade_out', 'breathing', 'pulse', 'transition',
                  'cyber_morph', 'system_awakening', 'target_lock', 'mission_complete',
                  'warning', 'shutdown')
PIXEL_EFFECTS = ('progressive_reveal', 'chase', 'rainbow_wave', 'scanner_sweep')
EffectName = Literal['solid', 'fade_in', 'fade_out', 'breathing', 'pulse', 'transition',
                     'cyber_morph', 'system_awakening', 'target_lock', 'mission_complete',
                     'warning', 'shutdown', 'progressive_reveal', 'chase', 'rainbow_wave',
                     'scanner_sweep']
PARAMETERS = {
    'solid': {'color', 'brightness'},
    'fade_in': {'color', 'duration_ms', 'brightness', 'easing'},
    'fade_out': {'color', 'duration_ms', 'brightness', 'easing'},
    'breathing': {'color', 'min_brightness', 'brightness', 'duration_ms', 'repeat'},
    'pulse': {'color', 'pulse_duration_ms', 'interval_ms', 'brightness', 'count', 'repeat'},
    'transition': {'from_color', 'color', 'duration_ms', 'brightness', 'easing'},
    'cyber_morph': {'duration_ms', 'brightness', 'repeat'},
    'system_awakening': {'duration_ms', 'brightness'},
    'target_lock': {'duration_ms', 'brightness'},
    'mission_complete': {'duration_ms', 'brightness'},
    'warning': {'duration_ms', 'brightness', 'repeat'},
    'shutdown': {'duration_ms', 'brightness'},
    'progressive_reveal': {'color', 'brightness', 'duration_ms', 'direction', 'repeat'},
    'chase': {'color', 'brightness', 'speed', 'direction', 'segment_length', 'repeat'},
    'rainbow_wave': {'brightness', 'speed', 'direction', 'repeat'},
    'scanner_sweep': {'color', 'brightness', 'speed', 'segment_length', 'direction', 'repeat'},
}


class EffectRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    effect: EffectName
    color: str = Field(default='#2563EB', pattern=r'^#[0-9a-fA-F]{6}$')
    from_color: str = Field(default='#FFFFFF', pattern=r'^#[0-9a-fA-F]{6}$')
    brightness: float = Field(default=80, ge=0, le=100)
    min_brightness: float = Field(default=5, ge=0, le=100)
    duration_ms: int = Field(default=2000, ge=100, le=120000)
    easing: Literal['linear', 'ease_in', 'ease_out', 'ease_in_out'] = 'ease_in_out'
    repeat: bool = False
    pulse_duration_ms: int = Field(default=500, ge=100, le=10000)
    interval_ms: int = Field(default=500, ge=0, le=10000)
    count: int = Field(default=3, ge=1, le=100)
    speed: float = Field(default=2, ge=0.1, le=30)
    direction: Literal['forward', 'reverse'] = 'forward'
    segment_length: int = Field(default=5, ge=1, le=1024)

    @model_validator(mode='after')
    def validate_parameters(self):
        invalid = self.model_fields_set - PARAMETERS[self.effect] - {'effect'}
        if invalid:
            raise ValueError(f'Parameters not supported by {self.effect}: {sorted(invalid)}')
        if self.effect == 'breathing' and self.min_brightness > self.brightness:
            raise ValueError('min_brightness must not exceed brightness')
        return self


def rgb(hex_color: str) -> RGB:
    return tuple(int(hex_color[index:index + 2], 16) for index in (1, 3, 5))


def easing(progress, name='ease_in_out'):
    progress = min(1.0, max(0.0, progress))
    return {'linear': lambda: progress, 'ease_in': lambda: progress * progress,
            'ease_out': lambda: 1 - (1 - progress) ** 2,
            'ease_in_out': lambda: progress * progress * (3 - 2 * progress)}[name]()


def interpolate(start: RGB, end: RGB, progress: float) -> RGB:
    return tuple(round(a + (b - a) * min(1, max(0, progress))) for a, b in zip(start, end))


def scale(color: RGB, brightness: float) -> RGB:
    return tuple(round(channel * min(100, max(0, brightness)) / 100) for channel in color)


@dataclass(frozen=True)
class LightingFrame:
    color: RGB
    brightness: float
    pixels: tuple[RGB, ...] | None = None
    done: bool = False

    @property
    def output_rgb(self):
        return scale(self.color, self.brightness)


def keyframes(elapsed, duration, stops):
    progress = min(1, elapsed / duration)
    for (left, color_a, level_a), (right, color_b, level_b) in zip(stops, stops[1:]):
        if progress <= right:
            amount = easing((progress - left) / (right - left))
            return interpolate(color_a, color_b, amount), level_a + (level_b - level_a) * amount
    return stops[-1][1:]


# ============================================================
# Global effects share the same renderer in simulation and DMX.
# ============================================================

def render_effect(request: EffectRequest, elapsed: float, pixel_count=0) -> LightingFrame:
    if request.effect in PIXEL_EFFECTS:
        from lighting_api.lighting_pixels import render_pixels
        return render_pixels(request, elapsed, pixel_count)
    elapsed = max(0, elapsed)
    duration = request.duration_ms / 1000
    progress = min(1, elapsed / duration)
    color = rgb(request.color)
    level = request.brightness
    done = False
    effect = request.effect
    if effect in ('fade_in', 'fade_out'):
        amount = easing(progress, request.easing)
        level *= amount if effect == 'fade_in' else 1 - amount
        done = progress >= 1
    elif effect in ('breathing', 'warning'):
        if effect == 'warning':
            color = (255, 160, 0)
        phase = elapsed / duration if request.repeat else min(1, elapsed / duration)
        minimum = request.min_brightness if effect == 'breathing' else min(5, request.brightness)
        level = minimum + (request.brightness - minimum) * (1 - math.cos(phase * 2 * math.pi)) / 2
        done = not request.repeat and progress >= 1
    elif effect == 'pulse':
        pulse = request.pulse_duration_ms / 1000
        cycle = pulse + request.interval_ms / 1000
        done = not request.repeat and elapsed >= cycle * request.count
        phase = elapsed % cycle
        level *= math.sin(math.pi * phase / pulse) ** 2 if phase < pulse and not done else 0
    elif effect == 'transition':
        color = interpolate(rgb(request.from_color), color, easing(progress, request.easing))
        done = progress >= 1
    elif effect == 'cyber_morph':
        phase = (elapsed / duration) % 3 if request.repeat else min(3, elapsed / duration)
        colors = ((0, 60, 255), (0, 255, 255), (150, 0, 255), (0, 60, 255))
        index = min(2, int(phase))
        color = interpolate(colors[index], colors[index + 1], easing(phase - index))
        level *= .7 + .3 * (1 - math.cos(phase * 2 * math.pi)) / 2
        done = not request.repeat and elapsed >= duration * 3
    elif effect in ('system_awakening', 'target_lock', 'mission_complete', 'shutdown'):
        blue, white, red, green = (0, 60, 255), (255, 255, 255), (255, 0, 0), (0, 255, 0)
        sequences = {
            'system_awakening': [(0, blue, 0), (.12, blue, 15), (.24, blue, 0),
                                 (.4, blue, 40), (.52, blue, 5), (1, blue, 100)],
            'target_lock': [(0, white, 100), (.4, (255, 100, 0), 100), (.7, red, 100),
                            (.8, red, 15), (.9, red, 100), (1, red, 100)],
            'mission_complete': [(0, rgb(request.from_color), 100), (.35, green, 100), (.6, green, 35),
                                 (.85, green, 100), (1, green, 100)],
            'shutdown': [(0, rgb(request.from_color), 100), (.55, blue, 15), (1, blue, 0)],
        }
        color, amount = keyframes(elapsed, duration, sequences[effect])
        level *= amount / 100
        done = progress >= 1
    return LightingFrame(color, level, done=done)


def effect_catalog(capabilities):
    fields = EffectRequest.model_json_schema()['properties']
    available = capabilities['supports_smooth_transitions']
    return [{
        'effect': name,
        'supported': capabilities['supports_progressive_effects'] if name in PIXEL_EFFECTS else available,
        'required_capability': 'supports_progressive_effects' if name in PIXEL_EFFECTS else 'supports_smooth_transitions',
        'parameters': {key: fields[key] for key in sorted(PARAMETERS[name])},
    } for name in GLOBAL_EFFECTS + PIXEL_EFFECTS]
