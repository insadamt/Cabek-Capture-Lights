"""Exercise real pyserial reads, writes and reconnects through a Linux pseudo-TTY.

Depends on pyserial and POSIX PTYs, with an emulated firmware peer. This verifies
host transport behavior without claiming physical USB or LED acceptance.
"""

import os
import select
from threading import Event, Thread

import pytest

pytest.importorskip("serial")

from lighting_api.lighting_config import LightingSettings
from lighting_api.lighting_protocol import COLORS, SerialLightingLink
from lighting_api.lighting_service import LightingService
from firmware_fake import FirmwareSerial


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
    settings = LightingSettings(port=str(stable_port), timeout=.3)
    link = SerialLightingLink(settings)
    service = LightingService(settings, link)
    try:
        for name, (command, _) in COLORS.items():
            link.set_color(name)
            assert first.firmware.command == command
        service.desired_output = (255, 0, 0)
        service.synchronize()
        assert first.firmware.command == "1"
        link.close()
        service.acknowledged_output = None
        stable_port.unlink()
        service.synchronize()
        assert link.port is None and service.last_error
        stable_port.symlink_to(second.device)
        service.next_connect = 0
        service.synchronize()
        assert link.port is not None and second.firmware.command == "1"
        assert service.acknowledged_output == (255, 0, 0)
    finally:
        link.close()
        first.close()
        second.close()
