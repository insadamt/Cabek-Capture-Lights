"""Schedule lighting commands and render effects through one serial-owning worker.

Depends on deterministic effects and SerialLightingLink. HTTP waits only for the
first acknowledged frame; later failures are logged and retried after USB loss.
"""
from collections import deque
from concurrent.futures import Future
from dataclasses import dataclass
import logging
from threading import Condition, Thread
import time

from lighting_api.errors import LightingError
from lighting_api.lighting_effects import EffectRequest, render_effect
from lighting_api.lighting_protocol import SerialLightingLink

logger = logging.getLogger(__name__)


@dataclass
class PendingCommand:
    request: EffectRequest | None
    generation: int
    result: Future


class LightingService:
    def __init__(self, settings, link=None, clock=time.monotonic):
        self.settings = settings
        self.link = link or SerialLightingLink(settings)
        self.clock = clock
        self.condition = Condition()
        self.pending = deque()
        self.generation = 0
        self.active = None
        self.started_at = 0
        self.start_color = (0, 0, 0)
        self.desired_output = None
        self.acknowledged_output = None
        self.next_connect = 0
        self.next_health = 0
        self.last_error = None
        self.stopping = False
        self.thread = None

    def start(self):
        with self.condition:
            if self.thread is None:
                self.thread = Thread(target=self.run, name='lighting-animation', daemon=True)
                self.thread.start()

    def submit(self, request: EffectRequest | None):
        result = Future()
        with self.condition:
            if self.stopping or self.thread is None:
                raise LightingError(503, 'service_unavailable', 'Lighting worker is unavailable.')
            self.generation += 1
            self.active = None
            # Keep queued OFF commands ahead of SET; superseded SET callers get a clear error.

            for command in list(self.pending):
                if command.request is not None:
                    self.pending.remove(command)
                    command.result.set_exception(LightingError(409, 'superseded', 'Replaced by a newer lighting command.'))
            command = PendingCommand(request, self.generation, result)
            if request is None:
                self.pending.appendleft(command)
                self.desired_output = (0, 0, 0)
            else:
                self.pending.append(command)
            self.condition.notify()
        return result.result()

    def set_effect(self, request):
        return self.submit(request)

    def off(self):
        return self.submit(None)

    def run(self):
        try:
            while True:
                with self.condition:
                    if self.stopping:
                        break
                    command = self.pending.popleft() if self.pending else None
                if command is not None:
                    self.execute_command(command)
                    continue
                self.synchronize()
                with self.condition:
                    if not self.pending and not self.stopping:
                        self.condition.wait(1 / self.settings.update_hz)
        finally:
            try:
                if self.link.port is not None:
                    self.link.set_color('OFF')
            except OSError:
                logger.warning('Could not acknowledge shutdown OFF')
            self.link.close()

    def execute_command(self, command):
        request = command.request
        try:
            self.link.connect()
            if request is not None and request.effect != 'solid':
                self.link.require_rgb()
            start_color = self.acknowledged_output or (0, 0, 0)
            output = (0, 0, 0) if request is None else render_effect(request, 0, start_color).output_rgb
            # Initial frames are always acknowledged, even when the requested RGB is unchanged.

            self.link.send_output(output)
            self.acknowledged_output = output
            self.last_error = None
            self.next_health = self.clock() + self.settings.health_seconds
            with self.condition:
                if command.generation == self.generation:
                    self.start_color = start_color
                    self.started_at = self.clock()
                    self.active = request
                    self.desired_output = output
            response = {'success': True, 'status': 'off'} if request is None else {
                'success': True, 'effect': request.effect,
                'status': 'active' if request.effect == 'solid' else 'running',
            }
            command.result.set_result(response)
        except LightingError as error:
            command.result.set_exception(error)
        except OSError as error:
            self.record_failure(error)
            # A failed request is rejected, rather than unexpectedly activated on reconnect.

            command.result.set_exception(LightingError(503, 'hardware_unavailable',
                                                     f'ESP32 command could not be delivered: {error}'))

    def synchronize(self):
        now = self.clock()
        if now < self.next_connect:
            return
        with self.condition:
            generation = self.generation
            active = self.active
            frame = render_effect(active, now - self.started_at, self.start_color) if active else None
            if frame is not None:
                self.desired_output = frame.output_rgb
            output = self.desired_output
            if self.pending:
                return
        if output is None:
            return
        try:
            self.link.connect()
            if active is not None and active.effect != 'solid':
                self.link.require_rgb()
            with self.condition:
                if generation != self.generation or self.pending:
                    return
            if output != self.acknowledged_output:
                self.link.send_output(output)
                self.acknowledged_output = output
                self.next_health = now + self.settings.health_seconds
            elif now >= self.next_health:
                status = self.link.query_status()
                # A device reboot or another writer invalidates the last acknowledged output.

                if status.get('rgb') != ','.join(map(str, output)):
                    self.acknowledged_output = None
                self.next_health = now + self.settings.health_seconds
            self.last_error = None
            with self.condition:
                if frame is not None and frame.done and generation == self.generation:
                    self.active = None
        except LightingError as error:
            logger.error('Lighting animation stopped: %s', error.message)
            with self.condition:
                if generation == self.generation:
                    self.active = None
                    self.desired_output = None
            self.last_error = error.message
        except OSError as error:
            self.record_failure(error)

    def record_failure(self, error):
        message = str(error)
        if message != self.last_error:
            logger.warning('Lighting unavailable: %s', message)
        self.last_error = message
        self.link.close()
        self.acknowledged_output = None
        self.next_connect = self.clock() + self.settings.reconnect_seconds

    def close(self):
        with self.condition:
            self.stopping = True
            self.active = None
            for command in self.pending:
                command.result.set_exception(LightingError(503, 'service_unavailable', 'Lighting worker is stopping.'))
            self.pending.clear()
            self.condition.notify()
        if self.thread is not None:
            self.thread.join(timeout=self.settings.timeout * 4 + 2)
