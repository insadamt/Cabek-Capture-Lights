"""Exercise the production serial parser and bridge against an in-memory ESP32.

Depends on the actual firmware's ASCII command contract; simulated DMX counters
verify status health but do not validate physical RS485 or LED colors.
"""

import pytest

from lighting_api.lighting_config import LightingSettings
from lighting_api.lighting_protocol import COLORS, SerialLightingLink
from lighting_api.lighting_service import LightingService


class FirmwareSerial:
    def __init__(self, **kwargs):
        self.options = kwargs
        self.command = "0"
        self.input = bytearray()
        self.writes = []
        self.uptime = 1000
        self.frames = 40
        self.open_count = 0
        self.closed = False
        self.broken = False
        self.inject = None

    def open(self):
        self.closed = False
        self.open_count += 1

    def close(self):
        self.closed = True

    def reset_input_buffer(self):
        self.input.clear()

    def read(self, size):
        data = bytes(self.input[:size])
        del self.input[:size]
        return data

    def write(self, data):
        if self.broken:
            raise OSError("USB disconnected")
        self.writes.append(data)
        if self.inject is not None:
            self.input.extend(self.inject)
            self.inject = None
            return len(data)
        command = data.decode()
        if command in ("\n", "\r", " ", "\t"):
            return len(data)
        if command == "?":
            self.uptime += 200
            self.frames += 8
            color = next(name for name, value in COLORS.items() if value[0] == self.command)
            rgb = ','.join(map(str, COLORS[color][1]))
            line = (f"STATUS firmware=cabek-dmx-v1 mode=dmx_tx command={self.command} "
                    f"rgb={rgb} errors=0 frames={self.frames} uptime_ms={self.uptime} "
                    "uart0_baud=115201 uart2_baud=250000\n")
        else:
            self.command = command
            color = next(name for name, value in COLORS.items() if value[0] == command)
            line = f"OK {command} {color} {' '.join(map(str, COLORS[color][1]))}\n"
        self.input.extend(line.encode())
        return len(data)


def make_bridge():
    now = [0.0]
    settings = LightingSettings(enabled=True, port="/dev/serial/by-id/test", timeout=.01)
    ports = []

    def factory(**kwargs):
        port = FirmwareSerial(**kwargs)
        ports.append(port)
        return port

    link = SerialLightingLink(settings, factory)
    service = LightingService(settings, link, lambda: now[0])
    service.state.transition("BOOTING")
    return service, ports, now


def test_all_legacy_commands_status_and_no_redundant_writes():
    service, ports, _ = make_bridge()
    service.synchronize()
    port = ports[0]
    assert port.options["exclusive"] is True
    assert not port.dtr and not port.rts
    for color, (command, _) in COLORS.items():
        result = service.link.set_color(color)
        assert result["command"] == command
    service.synchronize()
    count = len(port.writes)
    for _ in range(100):
        service.synchronize()
    assert len(port.writes) == count
    assert port.open_count == 1
    service.disconnect()


def test_blink_disconnect_reconnect_and_resynchronize_latest_scan():
    service, ports, now = make_bridge()
    service.synchronize()
    assert ports[0].command == "2"
    now[0] = .5
    service.synchronize()
    assert ports[0].command == "0"
    ports[0].broken = True
    now[0] = 1
    service.synchronize()
    assert not service.status()["esp32_available"]
    assert service.status()["last_error"]
    assert service.status()["acknowledged_color"] is None
    service.state.begin_capture("active")
    now[0] = 3
    service.synchronize()
    assert len(ports) == 2 and ports[1].command == "1"
    status = service.status()
    assert status["state"] == "SCANNING" and status["synchronized"]
    assert status["last_error"] is None
    service.disconnect()


@pytest.mark.parametrize("response", [b"OK 4 WHITE 255 255 255\n", b"OK 2 BLUE 0 0 1\n",
                                       b"BOOT firmware=cabek-dmx-v1\n", b"\xff\n", b"FAULT DMX\n", b""])
def test_bad_acknowledgments_never_claim_success(response):
    service, ports, _ = make_bridge()
    service.link.connect()
    ports[0].inject = response
    with pytest.raises((OSError, TimeoutError)):
        service.link.set_color("BLUE")
    assert service.last_successful_command is None
    service.disconnect()


def test_esp32_reboot_and_stalled_dmx_force_reconnect():
    service, ports, now = make_bridge()
    service.synchronize()
    ports[0].uptime = 0
    now[0] = 5
    service.synchronize()
    assert not service.connected
    now[0] = 7
    service.synchronize()
    assert service.connected
    ports[1].inject = (f"STATUS firmware=cabek-dmx-v1 mode=dmx_tx command=2 rgb=0,0,255 errors=0 "
                       f"frames={ports[1].frames} uptime_ms={ports[1].uptime + 500} "
                       "uart0_baud=115201 uart2_baud=250000\n").encode()
    now[0] = 12
    service.synchronize()
    assert not service.connected
    service.disconnect()


def test_auto_detection_rejects_ambiguous_devices(monkeypatch):
    monkeypatch.setattr("lighting_api.lighting_protocol.glob", lambda pattern: ["one", "two"])
    with pytest.raises(OSError, match="exactly one"):
        SerialLightingLink(LightingSettings()).connect()


def test_unavailable_hardware_keeps_state_and_retries_with_backoff():
    service, ports, now = make_bridge()
    service.link.serial_factory = lambda **kwargs: (_ for _ in ()).throw(OSError("missing USB"))
    service.state.begin_capture("scan")
    for _ in range(100):
        service.synchronize()
    assert not ports
    assert service.status()["state"] == "SCANNING"
    assert not service.status()["synchronized"]
    assert service.next_connect == 2
    now[0] = 2
    service.synchronize()
    assert service.next_connect == 4


def test_desired_state_changes_during_io_are_reported_unsynchronized():
    service, ports, _ = make_bridge()
    original = service.link.set_color

    def delayed(color):
        result = original(color)
        service.state.begin_capture("new")
        return result

    service.link.set_color = delayed
    service.synchronize()
    status = service.status()
    assert status["state"] == "SCANNING"
    assert status["acknowledged_color"] == "BLUE"
    assert status["synchronized"] is False
    service.link.set_color = original
    service.synchronize()
    assert service.status()["synchronized"]
    service.disconnect()


def test_deadline_expires_without_usb_and_without_status_polling():
    service, _, now = make_bridge()
    service.link.serial_factory = lambda **kwargs: (_ for _ in ()).throw(OSError("missing USB"))
    service.state.begin_capture("scan")
    service.state.set_readiness(None)
    service.state.finish_capture("scan", True)
    service.synchronize()
    now[0] = 10
    service.synchronize()
    assert service.state.state == "READY"


def test_slow_readiness_probe_does_not_delay_serial_capture():
    from threading import Event

    service, _, _ = make_bridge()
    service.state.transition("OFF")
    entered, release, red_acknowledged = Event(), Event(), Event()
    original = service.link.set_color

    def record_color(color):
        result = original(color)
        if color == "RED":
            red_acknowledged.set()
        return result

    def slow_probe():
        entered.set()
        assert release.wait(3)

    service.link.set_color = record_color
    service.start()
    try:
        service.initialize()
        service.set_readiness_probe(slow_probe)
        assert entered.wait(1)
        service.state.begin_capture("scan")
        assert red_acknowledged.wait(1)
    finally:
        release.set()
        service.close()
    assert not service.connected
    assert service.state.state == "OFF"
