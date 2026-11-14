#!/usr/bin/env python3
"""Check negotiated RGB commands, legacy compatibility and bounded animation soak.

Depends on pyserial, test_serial.Console and the exact flashed firmware binary.
Requires an idle exclusive port; records acknowledgments, never visible LED proof.
"""

import argparse
import hashlib
import json
from pathlib import Path
import time

import serial

from test_serial import Console, require


def query_rgb(console, expected, sketch):
    console.port.write(b'?')
    status = dict(part.split('=', 1) for part in console.wait_for('STATUS ').split()[1:])
    require(status['firmware'] == 'cabek-dmx-v1' and status.get('protocol') == 'rgb8-v1',
            'Extended firmware required')
    require(status['sketch'] == sketch and status['mode'] == 'dmx_tx', 'Unexpected firmware image/mode')
    require(status['rgb'] == ','.join(map(str, expected)), 'RGB did not persist')
    require(status['errors'] == '0', 'DMX errors reported')
    require(status['uart2_baud'] == '250000' and abs(int(status['uart0_baud']) - 115200) <= 12,
            'Unexpected UART baud')
    if console.previous_status:
        require(int(status['uptime_ms']) >= int(console.previous_status['uptime_ms']), 'Unexpected reset')
        require(int(status['frames']) >= int(console.previous_status['frames']), 'Frame count regressed')
    console.previous_status = status
    return status


def set_rgb(console, color, sketch):
    console.port.write(('R ' + ' '.join(map(str, color)) + '\n').encode())
    require(console.wait_for('OK ') == 'OK R RGB ' + ' '.join(map(str, color)), 'RGB ACK mismatch')
    return query_rgb(console, color, sketch)


def run(args):
    sketch = hashlib.md5(args.firmware.read_bytes()).hexdigest()
    args.log.parent.mkdir(parents=True, exist_ok=True)
    port = serial.Serial(port=None, baudrate=115200, timeout=.05, write_timeout=1, exclusive=True)
    port.dtr = port.rts = False
    port.port = args.port
    with args.log.open('wb') as log, port:
        console = Console(port, log)
        try:
            port.write(b"\n")
            initial = set_rgb(console, (0, 0, 0), sketch)
            console.active = True
            for command in '12340':
                console.send_commands(command)
                console.query_status('dmx_tx', sketch, command)
            previous = (12, 128, 255)
            set_rgb(console, previous, sketch)
            for invalid in (b'R 256 0 0\n', b'R -1 0 0\n', b'R 1 2\n', b'R 1 2 3 4\n',
                            b'R ' + b'9' * 80 + b' 0 0\n'):
                port.write(invalid)
                console.wait_for('ERR RGB')
                query_rgb(console, previous, sketch)
            port.write(b'R 12')
            console.wait_for('ERR RGB timeout')
            port.write(b' 34 56\n')
            query_rgb(console, previous, sketch)
            deadline = time.monotonic() + args.soak_seconds
            index = 0
            baseline = query_rgb(console, previous, sketch)
            final = baseline
            while time.monotonic() < deadline:
                final = set_rgb(console, (index % 256, (index * 3) % 256, (index * 7) % 256), sketch)
                index += 1
                time.sleep(1 / 15)
            elapsed = int(final['uptime_ms']) - int(baseline['uptime_ms'])
            frames = int(final['frames']) - int(baseline['frames'])
            require(frames * 1000 / max(1, elapsed) >= 20, 'DMX refresh stalled')
            require(int(final['heap']) >= int(initial['heap']) - 1024, 'Sustained heap loss')
            return {'result': 'PASS', 'rgb_updates': index, 'final': final,
                    'physical_led_colors_verified': False, 'waveform_verified': False}
        finally:
            console.send_commands('0')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--firmware', type=Path, required=True)
    parser.add_argument('--log', type=Path, default=Path('.evidence/rgb-serial.bin'))
    parser.add_argument('--soak-seconds', type=float, default=30)
    args = parser.parse_args()
    if not 1 <= args.soak_seconds <= 3600:
        parser.error('soak duration must be 1–3600 seconds')
    print(json.dumps(run(args), indent=2))


if __name__ == '__main__':
    main()
