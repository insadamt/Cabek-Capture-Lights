"""Validate relevant effect parameters and render deterministic global RGB frames.

Depends on Pydantic and elapsed monotonic seconds; performs no hardware I/O.
Duration is one complete cycle, with speed applied once to elapsed time.
"""
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RGB = tuple[int, int, int]
GLOBAL_EFFECTS = ('solid', 'fade_in', 'fade_out', 'breathing', 'pulse', 'transition',
                  'color_cycle', 'cyber_morph', 'system_awakening', 'target_lock',
                  'mission_complete', 'warning', 'shutdown')
EffectName = Literal['solid', 'fade_in', 'fade_out', 'breathing', 'pulse', 'transition',
                     'color_cycle', 'cyber_morph', 'system_awakening', 'target_lock',
                     'mission_complete', 'warning', 'shutdown']
ANIMATION_PARAMETERS = {'brightness', 'speed', 'repeat', 'duration_ms', 'easing'}
PARAMETERS = {name: ANIMATION_PARAMETERS | {'color'} for name in GLOBAL_EFFECTS}
PARAMETERS['solid'] = {'color', 'brightness'}
for name in ('transition', 'color_cycle', 'cyber_morph'):
    PARAMETERS[name] |= {'colors'}
for name in ('color_cycle', 'cyber_morph', 'system_awakening', 'target_lock', 'mission_complete', 'warning', 'shutdown'):
    PARAMETERS[name] -= {'color'}


class EffectRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    effect: EffectName = 'solid'
    color: str = Field(default='#FFFFFF', pattern=r'^#[0-9a-fA-F]{6}$')
    brightness: float = Field(default=100, ge=0, le=100, allow_inf_nan=False)
    speed: float = Field(default=1, ge=0.1, le=5, allow_inf_nan=False)
    repeat: bool = False
    duration_ms: int = Field(default=2000, ge=1, le=120000)
    colors: tuple[str, ...] | None = None
    easing: Literal['linear', 'ease_in', 'ease_out', 'ease_in_out'] = 'ease_in_out'

    @model_validator(mode='before')
    @classmethod
    def keep_relevant_parameters(cls, values):
        if not isinstance(values, dict):
            return values
        effect = values.get('effect', 'solid')
        if not isinstance(effect, str) or effect not in PARAMETERS:
            return values
        known = set(cls.model_fields)
        # Irrelevant recognized fields are ignored, even if their values are invalid.

        selected = {k: v for k, v in values.items() if k not in known or k in PARAMETERS[effect] or k == 'effect'}
        if 'colors' in selected and isinstance(selected['colors'], list):
            selected['colors'] = tuple(selected['colors'])
        return selected

    @model_validator(mode='after')
    def validate_palette(self):
        if self.colors is not None:
            import re
            if not 2 <= len(self.colors) <= 32 or any(
                re.fullmatch(r'#[0-9a-fA-F]{6}', color) is None for color in self.colors
            ):
                raise ValueError('colors requires 2–32 HEX colors')
        if self.effect == 'color_cycle' and self.colors is None:
            raise ValueError('color_cycle requires colors')
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
    return tuple(round(channel * brightness / 100) for channel in color)


@dataclass(frozen=True)
class LightingFrame:
    output_rgb: RGB
    done: bool


def keyframes(progress, stops, curve):
    for (left, color_a, level_a), (right, color_b, level_b) in zip(stops, stops[1:]):
        if progress <= right:
            amount = easing((progress - left) / (right - left), curve)
            return interpolate(color_a, color_b, amount), level_a + (level_b - level_a) * amount
    return stops[-1][1:]


# ============================================================
# Global animations reuse interpolation and keyframe choreography.
# ============================================================

def render_effect(request: EffectRequest, elapsed: float, start_color: RGB = (0, 0, 0)) -> LightingFrame:
    if request.effect == 'solid':
        return LightingFrame(scale(rgb(request.color), request.brightness), True)
    cycles = max(0, elapsed) * request.speed / (request.duration_ms / 1000)
    progress = cycles % 1 if request.repeat else min(1, cycles)
    done = not request.repeat and cycles >= 1
    color = rgb(request.color)
    level = 100
    effect = request.effect
    amount = easing(progress, request.easing)
    if effect in ('fade_in', 'fade_out'):
        level = 100 * (amount if effect == 'fade_in' else 1 - amount)
    elif effect in ('breathing', 'pulse', 'warning'):
        if effect == 'warning':
            color = (255, 160, 0)
        if effect == 'pulse' and progress >= .6:
            level = 0
        else:
            phase = progress / .6 if effect == 'pulse' else progress
            level = 100 * easing(1 - abs(2 * phase - 1), request.easing)
    elif effect in ('transition', 'color_cycle', 'cyber_morph'):
        if request.colors:
            palette = tuple(map(rgb, request.colors))
        elif effect == 'cyber_morph':
            palette = ((0, 60, 255), (0, 255, 255), (150, 0, 255))
        else:
            palette = (start_color, color)
        if effect in ('color_cycle', 'cyber_morph'):
            palette += (palette[0],)
        position = progress * (len(palette) - 1)
        index = min(len(palette) - 2, int(position))
        color = interpolate(palette[index], palette[index + 1], easing(position - index, request.easing))
    else:
        blue, white, red, green = (0, 60, 255), (255, 255, 255), (255, 0, 0), (0, 255, 0)
        sequences = {
            'system_awakening': [(0, blue, 0), (.12, blue, 15), (.24, blue, 0),
                                 (.4, blue, 40), (.52, blue, 5), (1, blue, 100)],
            'target_lock': [(0, white, 100), (.4, (255, 100, 0), 100), (.7, red, 100),
                            (.8, red, 15), (.9, red, 100), (1, red, 100)],
            'mission_complete': [(0, start_color, 100), (.35, green, 100), (.6, green, 35),
                                 (.85, green, 100), (1, green, 100)],
            'shutdown': [(0, start_color, 100), (.55, blue, 15), (1, blue, 0)],
        }
        color, level = keyframes(progress, sequences[effect], request.easing)
    return LightingFrame(scale(color, request.brightness * level / 100), done)
