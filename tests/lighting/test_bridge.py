"""Verify legacy/RGB delivery, acknowledgments and persistence with fake firmware.

Depends on the production serial link; no USB or physical DMX tests are claimed.
"""
from concurrent.futures import ThreadPoolExecutor

import pytest

from firmware_fake import FirmwareSerial
from lighting_api.errors import LightingError
from lighting_api.lighting_config import LightingSettings
from lighting_api.lighting_protocol import COLORS, SerialLightingLink


def make_link(rgb=True):
    settings = LightingSettings(port='fake', timeout=.01)
    ports = []
    def factory(**kwargs):
        port = FirmwareSerial(rgb=rgb, **kwargs)
        ports.append(port)
        return port
    return SerialLightingLink(settings, factory), ports


def test_all_legacy_colors_without_handshake_or_firmware_validation():
    link, ports = make_link(rgb=False)
    try:
        for name, (command, output) in COLORS.items():
            link.set_color(name)
            assert ports[0].command == command and ports[0].output == output
        assert b'?' not in ports[0].writes
        assert ports[0].open_count == 1
        assert not ports[0].dtr and not ports[0].rts
        assert ports[0].options['exclusive']
    finally:
        link.close()


def test_custom_rgb_capability_is_checked_once_and_writes_are_thread_safe():
    link, ports = make_link()
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda index: link.set_rgb((index, 23, 45)), range(40)))
        assert ports[0].writes.count(b'?') == 1
        assert len([write for write in ports[0].writes if write.startswith(b'R ')]) == 40
        assert ports[0].open_count == 1
    finally:
        link.close()


def test_legacy_firmware_rejects_rgb_and_remains_usable():
    link, ports = make_link(rgb=False)
    try:
        with pytest.raises(LightingError) as error:
            link.set_rgb((12, 34, 56))
        assert error.value.status_code == 501
        assert not any(write.startswith(b'R ') for write in ports[0].writes)
        link.set_color('WHITE')
        assert ports[0].output == (255, 255, 255)
    finally:
        link.close()


@pytest.mark.parametrize('response', [b'OK 4 WHITE 255 255 255\n', b'OK 2 BLUE 0 0 1\n',
                                    b'\xff\n', b'FAULT DMX\n', b''])
def test_bad_acknowledgments_never_claim_delivery(response):
    link, ports = make_link()
    link.connect()
    ports[0].inject = response
    try:
        with pytest.raises(OSError):
            link.set_color('BLUE')
    finally:
        link.close()


def test_mismatched_rgb_ack_and_short_write_are_rejected():
    link, ports = make_link()
    link.connect()
    link.require_rgb()
    try:
        ports[0].inject = b'OK R RGB 1 2 4\n'
        with pytest.raises(OSError, match='acknowledgment'):
            link.set_rgb((1, 2, 3))
        ports[0].write = lambda data: 0
        with pytest.raises(OSError, match='Incomplete'):
            link.set_color('OFF')
    finally:
        link.close()


def test_auto_detection_rejects_ambiguity_and_failed_open_closes_port(monkeypatch):
    monkeypatch.setattr('lighting_api.lighting_protocol.glob', lambda pattern: ['one', 'two'])
    with pytest.raises(OSError, match='exactly one'):
        SerialLightingLink(LightingSettings()).connect()
    link, ports = make_link()
    original = link.serial_factory
    def broken(**kwargs):
        port = original(**kwargs)
        def fail():
            raise OSError('missing USB')
        port.open = fail
        return port
    link.serial_factory = broken
    with pytest.raises(OSError, match='missing USB'):
        link.connect()
    assert ports[0].closed and link.port is None
