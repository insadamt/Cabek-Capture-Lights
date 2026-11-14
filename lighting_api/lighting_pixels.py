"""Render logical LED zones without assuming any physical controller protocol.

Depends on the pure lighting frame model. A zone can represent several physical
LEDs; only the explicit simulation driver currently accepts these frames.
"""

import colorsys
import math

from lighting_api.lighting_effects import LightingFrame, rgb, scale


def render_pixels(request, elapsed, count):
    if count < 1:
        raise ValueError('Zone effects require at least one independently controlled zone')
    elapsed = max(0, elapsed)
    color = scale(rgb(request.color), request.brightness)
    pixels = [(0, 0, 0)] * count
    reverse = request.direction == 'reverse'
    done = False
    if request.effect == 'progressive_reveal':
        progress = elapsed / (request.duration_ms / 1000)
        done = not request.repeat and progress >= 1
        fraction = progress % 1 if request.repeat else min(1, progress)
        pixels[:int(count * fraction)] = [color] * int(count * fraction)
    elif request.effect == 'rainbow_wave':
        progress = elapsed * request.speed / count
        done = not request.repeat and progress >= 1
        phase = progress % 1 if request.repeat else min(1, progress)
        pixels = [scale(tuple(round(c * 255) for c in colorsys.hsv_to_rgb(
            (index / count - phase) % 1, 1, 1)), request.brightness) for index in range(count)]
    else:
        length = min(request.segment_length, count)
        travel = max(0, count - length)
        distance = elapsed * request.speed
        if request.effect == 'scanner_sweep':
            period = max(1, travel * 2)
            done = not request.repeat and distance >= period
            distance = distance % period if request.repeat else min(period, distance)
            position = round(travel - abs(travel - distance)) if travel else 0
        else:
            period = count + length
            done = not request.repeat and distance >= period
            position = math.floor(distance % period if request.repeat else min(period, distance)) - length + 1
        for index in range(max(0, position), min(count, position + length)):
            pixels[index] = color
    if reverse:
        pixels.reverse()
    return LightingFrame(rgb(request.color), request.brightness, tuple(pixels), done)
