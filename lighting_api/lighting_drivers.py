"""Separate physical DMX RGB output from a memory-only logical zone simulator.

Depends on the existing serial link and validated settings. No unverified pixel
controller is implemented; mapping, color order and power ceilings are simulated.
"""

from typing import Protocol

from lighting_api.lighting_effects import RGB, scale
from lighting_api.lighting_protocol import COLORS


def capabilities(driver, *, smooth=False, zones=None, simulated=False):
    return dict(driver=driver, supports_global_rgb=True, supports_brightness=smooth,
                supports_smooth_transitions=smooth, supports_individual_pixels=False,
                supports_independent_zones=zones is not None,
                supports_progressive_effects=zones is not None, pixel_count=zones,
                simulated=simulated, physical_protocol_verified=False if simulated else None)


class LightingDriver(Protocol):
    def connect(self): ...
    def disconnect(self): ...
    def get_capabilities(self) -> dict: ...
    def set_global_color(self, color: RGB, brightness: float): ...
    def set_pixels(self, colors: tuple[RGB, ...]): ...
    def get_status(self) -> dict: ...


class DmxRgbDriver:
    def __init__(self, link):
        self.link = link

    def connect(self):
        return self.link.connect()

    def disconnect(self):
        self.link.close()

    def get_capabilities(self):
        status = self.link.previous_status or {}
        return capabilities('dmx_rgb', smooth=status.get('protocol') == 'rgb8-v1')

    def set_global_color(self, color, brightness):
        output = scale(color, brightness)
        for name, (_, value) in COLORS.items():
            if output == value:
                return self.link.set_color(name)
        return self.link.set_rgb(output)

    def set_pixels(self, colors):
        raise ValueError('The RGB DMX decoder cannot address independent zones')

    def get_status(self):
        return self.link.query_status()


class SimulatedPixelDriver:
    def __init__(self, settings):
        self.settings = settings
        self.logical_pixels = tuple([(0, 0, 0)] * settings.pixel_count)
        self.physical_pixels = self.logical_pixels
        self.connected = False
        self.sequence = 0
        self.rgb = (0, 0, 0)

    def connect(self):
        self.connected = True
        return self.get_status()

    def disconnect(self):
        self.connected = False

    def get_capabilities(self):
        return capabilities('simulated_pixels', smooth=True, zones=self.settings.pixel_count, simulated=True)

    def set_global_color(self, color, brightness):
        self.rgb = scale(color, brightness)
        self.set_pixels(tuple([self.rgb] * self.settings.pixel_count))
        return self.get_status()

    def set_pixels(self, colors):
        if not self.connected or len(colors) != self.settings.pixel_count:
            raise ValueError('Simulator disconnected or incorrect zone count')
        self.logical_pixels = tuple(colors)
        mapped = [(0, 0, 0)] * len(colors)
        order = ['RGB'.index(channel) for channel in self.settings.color_order]
        mapping = self.settings.pixel_mapping or tuple(range(len(colors)))
        for logical, physical in enumerate(mapping):
            mapped[physical] = tuple(colors[logical][channel] for channel in order)
        self.physical_pixels = tuple(mapped)
        self.sequence += 1
        return self.get_status()

    def get_status(self):
        return {'firmware': 'simulation', 'command': 'SIM', 'rgb': ','.join(map(str, self.rgb)),
                'sequence': str(self.sequence)}
