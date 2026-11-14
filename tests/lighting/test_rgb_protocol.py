"""Exercise RGB capability negotiation and serial confirmation using fake firmware.

Depends on the production serial parser; legacy tests separately verify every
unchanged single-byte command and real pseudo-TTY reconnection.
"""

import pytest

from lighting_api.lighting_config import LightingSettings
from lighting_api.lighting_effects import EffectRequest
from lighting_api.lighting_protocol import SerialLightingLink
from lighting_api.lighting_service import LightingService
from test_bridge import FirmwareSerial


class RgbFirmwareSerial(FirmwareSerial):
    def __init__(self, **options):
        super().__init__(**options)
        self.rgb = (0, 0, 0)

    def write(self, data):
        if self.broken:
            raise OSError('USB disconnected')
        if self.inject is not None:
            return super().write(data)
        if data.startswith(b'R '):
            self.writes.append(data)
            self.rgb = tuple(map(int, data.decode().split()[1:]))
            self.command = 'R'
            self.input.extend(('OK R RGB ' + ' '.join(map(str, self.rgb)) + '\n').encode())
            return len(data)
        if data == b'?':
            self.writes.append(data)
            self.uptime += 200
            self.frames += 8
            from lighting_api.lighting_protocol import COLORS
            output = self.rgb if self.command == 'R' else next(rgb for command, rgb in COLORS.values() if command == self.command)
            self.input.extend((f'STATUS firmware=cabek-dmx-v1 protocol=rgb8-v1 mode=dmx_tx command={self.command} '
                f'rgb={",".join(map(str, output))} errors=0 frames={self.frames} uptime_ms={self.uptime} '
                'uart0_baud=115201 uart2_baud=250000\n').encode())
            return 1
        return super().write(data)


def make_rgb_service():
    now = [0.0]
    ports = []
    settings = LightingSettings(enabled=True, port='fake', timeout=.01)
    def factory(**kwargs):
        ports.append(RgbFirmwareSerial(**kwargs))
        return ports[-1]
    service = LightingService(settings, SerialLightingLink(settings, factory), lambda: now[0])
    service.state.transition('INITIALIZING')
    service.state.set_readiness(None)
    service.synchronize()
    return service, now, ports


def test_rgb_round_trip_rejects_bad_ack_and_negotiates_legacy():
    service, _, ports = make_rgb_service()
    assert service.driver.get_capabilities()['supports_smooth_transitions']
    status = service.link.set_rgb((12, 34, 56))
    assert status['rgb'] == '12,34,56' and status['command'] == 'R'
    ports[0].inject = b'OK R RGB 12 34 57\n'
    with pytest.raises(OSError):
        service.link.set_rgb((12, 34, 56))
    service.disconnect()
    legacy = SerialLightingLink(service.settings, FirmwareSerial)
    legacy.connect()
    with pytest.raises(OSError, match='advertise'):
        legacy.set_rgb((12, 34, 56))
    legacy.close()


def test_rate_limit_deduplication_and_latest_frame_replay_after_usb_loss():
    service, now, ports = make_rgb_service()
    request = EffectRequest(effect='solid', color='#123456', brightness=100)
    service.engine.start_preview(request, service.driver.get_capabilities())
    now[0] = .1
    service.synchronize()
    count = len(ports[0].writes)
    for _ in range(100):
        service.synchronize()
    assert len(ports[0].writes) == count
    assert service.status()['synchronized']
    service.engine.start_preview(EffectRequest(effect='transition', color='#FF0000', duration_ms=1000), service.driver.get_capabilities())
    now[0] = .11
    service.synchronize()
    assert len(ports[0].writes) == count
    ports[0].broken = True
    now[0] = .5
    service.synchronize()
    assert not service.connected and not service.status()['synchronized']
    assert service.status()['acknowledged_rgb'] is None
    service.state.begin_capture('scan-during-disconnect')
    now[0] = 3
    service.synchronize()
    assert service.connected and len(ports) == 2
    assert service.status()['state'] == 'SCANNING'
    assert service.engine.preview is None
    assert service.status()['synchronized']
    service.disconnect()


def test_connect_drains_interrupted_packet_and_ignores_only_known_startup_responses():
    service, _, ports = make_rgb_service()
    assert ports[0].writes[0] == b'\n'
    service.disconnect()
    def interrupted(**kwargs):
        port = RgbFirmwareSerial(**kwargs)
        port.inject = b'ERR RGB: use R <0-255> <0-255> <0-255>\n'
        return port
    service.link.serial_factory = interrupted
    assert service.link.connect()['protocol'] == 'rgb8-v1'
    service.disconnect()
