"""Own one persistent, locked ESP32 serial connection without a boot handshake.

Depends on pyserial and the existing OK/STATUS ASCII protocol. Basic legacy
commands work immediately; only RGB operations inspect extension support.
"""
from glob import glob
from threading import RLock
import time

from lighting_api.errors import LightingError

COLORS = {'OFF': ('0', (0, 0, 0)), 'RED': ('1', (255, 0, 0)),
          'BLUE': ('2', (0, 0, 255)), 'GREEN': ('3', (0, 255, 0)),
          'WHITE': ('4', (255, 255, 255))}


class SerialLightingLink:
    def __init__(self, settings, serial_factory=None):
        self.settings = settings
        self.serial_factory = serial_factory
        self.port = None
        self.buffer = bytearray()
        self.previous_status = None
        self.lock = RLock()

    def connect(self):
        with self.lock:
            if self.port is not None:
                return
            if self.settings.port == 'auto':
                candidates = sorted(glob('/dev/serial/by-id/*'))
                if len(candidates) != 1:
                    raise OSError('Configure CABEK_LIGHTS_PORT: auto requires exactly one by-id device.')
                device = candidates[0]
            else:
                device = self.settings.port
            factory = self.serial_factory
            if factory is None:
                import serial
                factory = serial.Serial
            try:
                self.port = factory(port=None, baudrate=self.settings.baud, timeout=.02,
                                    write_timeout=self.settings.timeout, exclusive=True)
                # Set modem lines before open to avoid resetting the transmitting ESP32.

                self.port.dtr = False
                self.port.rts = False
                self.port.port = device
                self.port.open()
                self.buffer.clear()
                self.previous_status = None
                self.port.reset_input_buffer()
                # Drain interrupted RGB packets before any legacy digits can be interpreted.

                self.write('\n')
            except Exception:
                self.close()
                raise

    def close(self):
        with self.lock:
            try:
                if self.port is not None:
                    self.port.close()
            finally:
                self.port = None
                self.buffer.clear()
                self.previous_status = None

    def read_until(self, prefix):
        deadline = time.monotonic() + self.settings.timeout
        while time.monotonic() < deadline:
            if b'\n' in self.buffer:
                raw, _, remainder = self.buffer.partition(b'\n')
                self.buffer = bytearray(remainder)
                try:
                    line = raw.decode('ascii').strip()
                except UnicodeDecodeError as error:
                    raise OSError('Corrupt serial response.') from error
                if line.startswith(prefix):
                    return line
                if not line or line.startswith(('BOOT ', 'READY ', 'STATUS ', 'ERR RGB timeout',
                                               'ERR RGB:')):
                    continue
                raise OSError('ESP32 rejected the command or returned an unexpected response.')
            else:
                self.buffer.extend(self.port.read(512))
                if len(self.buffer) > 8192:
                    raise OSError('Serial response exceeded its limit.')
        raise TimeoutError('ESP32 response timed out.')

    def write(self, command):
        if self.port is None:
            raise OSError('ESP32 is disconnected.')
        if self.port.write(command.encode('ascii')) != len(command):
            raise OSError('Incomplete serial write.')

    def query_status(self):
        with self.lock:
            self.connect()
            self.write('?')
            line = self.read_until('STATUS ')
            try:
                status = dict(item.split('=', 1) for item in line.split()[1:])
                if not status:
                    raise ValueError('Empty status')
                if int(status.get('errors', '0')) != 0:
                    raise OSError('ESP32 reports DMX transmission errors.')
            except ValueError as error:
                raise OSError('Invalid ESP32 status.') from error
            self.previous_status = status
            return status

    def require_rgb(self):
        with self.lock:
            status = self.previous_status or self.query_status()
            if status.get('protocol') != 'rgb8-v1':
                raise LightingError(501, 'unsupported_firmware',
                                    'This effect or color requires firmware with the RGB command (rgb8-v1).')

    def set_color(self, color):
        with self.lock:
            self.connect()
            command, output = COLORS[color]
            self.write(command)
            expected = f"OK {command} {color} {' '.join(map(str, output))}"
            if self.read_until('OK ') != expected:
                raise OSError('ESP32 acknowledgment does not match the requested color.')

    def set_rgb(self, output):
        with self.lock:
            self.connect()
            self.require_rgb()
            payload = ' '.join(map(str, output))
            self.write('R ' + payload + '\n')
            if self.read_until('OK ') != 'OK R RGB ' + payload:
                raise OSError('ESP32 RGB acknowledgment does not match the requested output.')

    def send_output(self, output):
        with self.lock:
            for name, (_, color) in COLORS.items():
                if output == color:
                    self.set_color(name)
                    return
            self.set_rgb(output)
