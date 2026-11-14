"""Emulate the documented ESP32 serial protocol for software-only acceptance.

Depends on production legacy colors; never opens USB or simulates visible LEDs.
"""
from lighting_api.lighting_protocol import COLORS


class FirmwareSerial:
    def __init__(self, rgb=True, **kwargs):
        self.options = kwargs
        self.rgb_supported = rgb
        self.output = (0, 0, 0)
        self.command = '0'
        self.input = bytearray()
        self.writes = []
        self.open_count = 0
        self.closed = False
        self.broken = False
        self.inject = None

    def open(self):
        self.open_count += 1
        self.closed = False

    def close(self):
        self.closed = True

    def reset_input_buffer(self):
        self.input.clear()

    def read(self, size):
        result = bytes(self.input[:size])
        del self.input[:size]
        return result

    def write(self, data):
        if self.broken:
            raise OSError('USB disconnected')
        self.writes.append(data)
        if self.inject is not None:
            self.input.extend(self.inject)
            self.inject = None
            return len(data)
        text = data.decode().strip()
        if not text:
            return len(data)
        if text == '?':
            protocol = ' protocol=rgb8-v1' if self.rgb_supported else ''
            response = f'STATUS command={self.command} rgb={",".join(map(str, self.output))} errors=0{protocol}\n'
        elif text.startswith('R ') and self.rgb_supported:
            self.output = tuple(map(int, text.split()[1:]))
            self.command = 'R'
            response = f'OK R RGB {" ".join(map(str, self.output))}\n'
        elif text in '01234' and len(text) == 1:
            self.command = text
            name, (_, self.output) = next((name, value) for name, value in COLORS.items() if value[0] == text)
            response = f'OK {text} {name} {" ".join(map(str, self.output))}\n'
        else:
            response = 'ERR command: use 0-4 or ?\n'
        self.input.extend(response.encode())
        return len(data)
