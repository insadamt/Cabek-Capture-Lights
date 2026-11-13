#!/usr/bin/env python3
"""Exercise the real CABEK console and detect corruption, resets, and DMX stalls.

Depends on pyserial (also installed with PlatformIO) and matching staged firmware.
Records raw bytes; console acknowledgments do not prove physical LED colors/timing.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import serial


COLORS = {
    "0": ("OFF", "0,0,0"),
    "1": ("RED", "255,0,0"),
    "2": ("BLUE", "0,0,255"),
    "3": ("GREEN", "0,255,0"),
    "4": ("WHITE", "255,255,255"),
}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class Console:
    def __init__(self, port, log):
        self.port = port
        self.log = log
        self.buffer = bytearray()
        self.active = False
        self.bytes_read = 0
        self.previous_status = None

    def read_line(self, deadline):
        while time.monotonic() < deadline:
            if b"\n" in self.buffer:
                raw, _, remainder = self.buffer.partition(b"\n")
                self.buffer = bytearray(remainder)
                require(all(byte in (9, 13) or 32 <= byte <= 126 for byte in raw),
                        f"Corrupted serial bytes: {raw[:100]!r}")
                line = raw.decode("ascii").strip()
                require(not any(word in line.lower() for word in
                                ("guru meditation", "panic", "watchdog", "brownout",
                                 "backtrace:", "fault", "abort()", "loadstoreerror")),
                        f"Device failure: {line}")
                if self.active:
                    require(not line.startswith(("BOOT ", "ets ", "rst:", "READY")),
                            f"Unexpected reboot: {line}")
                return line
            data = self.port.read(4096)
            self.log.write(data)
            self.log.flush()
            self.bytes_read += len(data)
            self.buffer.extend(data)
            require(len(self.buffer) < 8192, "Serial stream has no line endings")
        raise AssertionError("Timed out waiting for a readable console response")

    def wait_for(self, prefix, timeout=4):
        deadline = time.monotonic() + timeout
        while True:
            line = self.read_line(deadline)
            if line.startswith(prefix):
                return line
            if self.active:
                require(not line, f"Unexpected response while waiting for {prefix!r}: {line}")

    def query_status(self, mode, sketch, command=None):
        self.port.write(b"?")
        line = self.wait_for("STATUS ")
        status = dict(item.split("=", 1) for item in line.split()[1:])
        require(status["firmware"] == "cabek-dmx-v1", "Wrong firmware version")
        require(status["mode"] == mode, f"Wrong diagnostic stage: {status['mode']}")
        require(status["sketch"] == sketch, "Board firmware differs from the expected binary")
        # A fractional hardware divider can report 115201 for requested 115200.
        require(abs(int(status["uart0_baud"]) - 115200) <= 12,
                "USB UART baud outside 0.01% of 115200")
        require(status["uart2_baud"] == ("0" if mode == "serial_only" else "250000"),
                "Unexpected DMX baud")
        require(status["xtal_mhz"] == "40", "Unexpected crystal frequency")
        require(status["errors"] == "0", "DMX error counter increased")
        if command is not None:
            require(status["command"] == command, "Selected command did not persist")
            require(status["rgb"] == COLORS[command][1], "Wrong RGB channel order")
        if self.previous_status:
            require(int(status["uptime_ms"]) >= int(self.previous_status["uptime_ms"]),
                    "Uptime regressed (possible reboot)")
            require(int(status["frames"]) >= int(self.previous_status["frames"]),
                    "Frame counter regressed")
        if mode != "dmx_tx":
            require(status["frames"] == "0", "Diagnostic stage unexpectedly transmitted DMX")
        self.previous_status = status
        return status

    def send_commands(self, commands):
        self.port.write(commands.encode("ascii"))
        self.port.flush()
        for command in commands:
            name, rgb = COLORS[command]
            response = self.wait_for("OK ")
            expected = f"OK {command} {name} {rgb.replace(',', ' ')}"
            require(response == expected, f"Wrong or missing acknowledgment: {response!r}")


def run(args):
    # Arduino's getSketchMD5 covers the application image length, including padding.
    sketch = hashlib.md5(args.firmware.read_bytes()).hexdigest()
    args.log.parent.mkdir(parents=True, exist_ok=True)
    port = serial.Serial(port=None, baudrate=115200, timeout=0.05,
                         write_timeout=2, exclusive=True)
    port.dtr = False
    port.rts = False
    port.port = args.port
    with args.log.open("wb") as log, port:
        console = Console(port, log)
        # Reset before testing to capture startup and prove the device starts OFF.
        port.rts = True
        time.sleep(0.1)
        port.reset_input_buffer()
        port.rts = False
        console.wait_for("READY ", timeout=8)
        console.wait_for("STATUS ")
        console.active = True
        initial = console.query_status(args.mode, sketch, "0")
        for command in "12340":
            console.send_commands(command)
            console.query_status(args.mode, sketch, command)
        console.port.write(b"x\r\n \t")
        require(console.wait_for("ERR ") == "ERR command: use 0-4 or ?",
                "Invalid command was not rejected")
        console.query_status(args.mode, sketch, "0")
        repeated = "1" * 25
        rapid = "01234" * 20
        console.send_commands(repeated)
        console.query_status(args.mode, sketch, "1")
        console.send_commands(rapid)
        baseline = console.query_status(args.mode, sketch, "4")
        end = time.monotonic() + args.soak_seconds
        final = baseline
        while time.monotonic() < end:
            time.sleep(min(1, max(0, end - time.monotonic())))
            final = console.query_status(args.mode, sketch, "4")
        elapsed_ms = int(final["uptime_ms"]) - int(baseline["uptime_ms"])
        frames = int(final["frames"]) - int(baseline["frames"])
        if args.mode == "dmx_tx":
            require(frames > 0, "DMX transmission stalled during idle hold")
            require(frames * 1000 / max(1, elapsed_ms) >= 20, "DMX refresh rate too low")
        require(int(final["heap"]) >= int(baseline["heap"]) - 1024,
                "Sustained heap loss during idle hold")
        console.send_commands("0")
        console.query_status(args.mode, sketch, "0")
        return {"result": "PASS", "mode": args.mode, "sketch": sketch,
                "commands": 131, "bytes_read": console.bytes_read,
                "soak_seconds": args.soak_seconds, "initial": initial, "final": final,
                "observed_frames_per_second": round(frames * 1000 / max(1, elapsed_ms), 2),
                "physical_led_colors_verified": False, "waveform_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--mode", choices=("serial_only", "dmx_init", "dmx_tx"), required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--soak-seconds", type=float, default=15)
    args = parser.parse_args()
    if args.soak_seconds <= 0:
        parser.error("--soak-seconds must be positive")
    try:
        print(json.dumps(run(args), indent=2))
    except (AssertionError, serial.SerialException, OSError, KeyError, ValueError) as error:
        print(json.dumps({"result": "FAIL", "reason": str(error)}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
