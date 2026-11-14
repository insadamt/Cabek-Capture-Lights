"""Exercise real pyserial reads, writes and reconnects through a Linux pseudo-TTY.

Depends on pyserial and POSIX PTYs, with an emulated firmware peer. This verifies
host transport behavior without claiming physical USB or LED acceptance.
"""

import os
from pathlib import Path
import select
from threading import Event, Thread

import pytest

pytest.importorskip("serial")

from lighting_api.lighting_config import LightingSettings
from lighting_api.lighting_protocol import COLORS, SerialLightingLink
from lighting_api.lighting_service import LightingService
from test_bridge import FirmwareSerial


class FirmwarePeer:
    def __init__(self):
        self.master, self.slave = os.openpty()
        self.device = os.ttyname(self.slave)
        self.firmware = FirmwareSerial()
        self.stopping = Event()
        self.thread = Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        while not self.stopping.is_set():
            readable, _, _ = select.select([self.master], [], [], .02)
            if readable:
                for command in os.read(self.master, 128):
                    self.firmware.write(bytes([command]))
                    response = self.firmware.read(4096)
                    os.write(self.master, response)

    def close(self):
        self.stopping.set()
        self.thread.join(timeout=1)
        os.close(self.master)
        os.close(self.slave)


def test_real_serial_session_and_reconnect_to_reenumerated_device(tmp_path):
    first, second = FirmwarePeer(), FirmwarePeer()
    stable_port = tmp_path / "stable-esp32"
    stable_port.symlink_to(first.device)
    settings = LightingSettings(enabled=True, port=str(stable_port), timeout=.3,
                                token="c" * 32, maintenance_token="m" * 32)
    service = LightingService(settings, SerialLightingLink(settings))
    try:
        service.state.transition("BOOTING")
        service.synchronize()
        assert service.connected
        for color, (command, _) in COLORS.items():
            assert service.link.set_color(color)["command"] == command
        service.state.begin_capture("capture")
        service.synchronize()
        assert first.firmware.command == "1"
        service.disconnect()
        stable_port.unlink()
        service.synchronize()
        assert not service.connected
        assert service.status()["state"] == "SCANNING"
        stable_port.symlink_to(second.device)
        service.next_connect = 0
        service.synchronize()
        assert service.connected and second.firmware.command == "1"
        assert service.status()["synchronized"]
    finally:
        service.disconnect()
        first.close()
        second.close()
