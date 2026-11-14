"""Arbitrate one effect against authoritative lifecycle state and preview deadlines.

Depends on the existing synchronized LightingState, pure renderers and driver
capabilities; the serial owner calls render without spawning per-effect workers.
"""

from lighting_api.errors import DossierError
from lighting_api.lighting_effects import EffectRequest, LightingFrame, PIXEL_EFFECTS, render_effect, scale
from lighting_api.lighting_protocol import COLORS


class LightingEngine:
    def __init__(self, state, settings):
        self.state = state
        self.settings = settings
        self.key = None
        self.request = None
        self.started = 0
        self.preview = None
        self.restore_started = None
        self.preview_revision = None
        self.preview_started = 0
        self.preview_deadline = None
        self.last_frame = LightingFrame((0, 0, 0), 0)
        self.active_effect = None

    def require_idle(self):
        if self.state.capture_id or self.state.state != 'READY' or not self.state.ready:
            raise DossierError(409, 'lighting_test_conflict', 'Effect preview requires an idle ready tunnel.')

    def start_preview(self, request, capabilities):
        with self.state.lock:
            self.require_idle()
            capability = 'supports_progressive_effects' if request.effect in PIXEL_EFFECTS else 'supports_smooth_transitions'
            if not capabilities[capability]:
                raise DossierError(409, 'lighting_unsupported_capability', f'Effect requires {capability}.')
            if request.effect in ('chase', 'scanner_sweep') and request.segment_length > capabilities['pixel_count']:
                raise DossierError(422, 'lighting_invalid_segment', 'Segment length exceeds the configured zone count.')
            if self.preview == request and self.preview_revision == self.state.revision and self.state.clock() < self.preview_deadline:
                return
            self.state.test_color = self.state.test_deadline = None
            self.preview = request
            self.preview_revision = self.state.revision
            self.preview_started = self.state.clock()
            self.preview_deadline = self.state.clock() + self.settings.preview_seconds
            self.key = None

    def stop_preview(self):
        with self.state.lock:
            self.require_idle()
            self.preview = None
            self.restore_started = self.state.clock()
            self.state.test_color = self.state.test_deadline = None
            self.key = None

    def lifecycle_request(self, snapshot):
        if snapshot['warning']:
            return EffectRequest(effect='warning', duration_ms=3000, brightness=70, repeat=True)
        choices = {
            'BOOTING': dict(effect='system_awakening', duration_ms=3000, brightness=80),
            'INITIALIZING': dict(effect='breathing', color='#003CFF', duration_ms=2500, brightness=70, repeat=True),
            'READY': dict(effect='transition', color='#FFFFFF', duration_ms=800, brightness=100),
            'SCANNING': dict(effect='target_lock', duration_ms=1200, brightness=100),
            'COMPLETED': dict(effect='mission_complete', duration_ms=1600, brightness=100),
            'OFF': (dict(effect='shutdown', duration_ms=1000, brightness=100) if any(self.last_frame.output_rgb)
                    else dict(effect='solid', color='#000000', brightness=0)),
        }
        return EffectRequest(**choices[snapshot['state']])

    def render(self, capabilities):
        with self.state.lock:
            snapshot = self.state.snapshot()
            now = self.state.clock()
            if self.preview is not None and (self.preview_revision != snapshot['revision'] or now >= self.preview_deadline):
                if self.preview_revision == snapshot['revision']:
                    self.restore_started = now
                self.preview = None
                self.key = None
            if not capabilities['supports_smooth_transitions'] or snapshot['test_active']:
                self.active_effect = 'legacy_test' if snapshot['test_active'] else 'legacy_lifecycle'
                if capabilities['supports_smooth_transitions']:
                    self.last_frame = LightingFrame(COLORS[snapshot['color']][1], self.settings.brightness_limit)
                else:
                    self.last_frame = (LightingFrame(COLORS[snapshot['color']][1], 100)
                                       if self.settings.brightness_limit == 100 else LightingFrame((0, 0, 0), 0))
                return self.last_frame
            key = (snapshot['revision'], self.preview)
            if key != self.key:
                self.key = key
                self.request = self.preview or self.lifecycle_request(snapshot)
                limit = self.settings.brightness_limit
                initial_rgb = scale(self.last_frame.color, self.last_frame.brightness * 100 / limit) if limit else (0, 0, 0)
                initial = '#' + ''.join(f'{channel:02X}' for channel in initial_rgb)
                if self.request.effect == 'fade_out' and 'color' not in self.request.model_fields_set:
                    self.request = self.request.model_copy(update={
                        'color': initial, 'brightness': (self.request.brightness
                            if 'brightness' in self.request.model_fields_set else 100)})
                if self.request.effect in ('transition', 'shutdown', 'mission_complete') and 'from_color' not in self.request.model_fields_set:
                    self.request = self.request.model_copy(update={'from_color': initial})
                self.started = self.preview_started if self.preview else (
                    self.restore_started if self.restore_started is not None else self.state.entered_at)
                self.restore_started = None
            self.active_effect = self.request.effect
            elapsed = now - self.started
            if not self.preview and snapshot['state'] == 'SCANNING' and elapsed >= 1.2:
                self.active_effect = 'pulse'
                request = EffectRequest(effect='pulse', color='#FF0000', pulse_duration_ms=1000,
                                        interval_ms=200, brightness=100, repeat=True)
                frame = render_effect(request, elapsed - 1.2)
            else:
                frame = render_effect(self.request, elapsed, capabilities['pixel_count'] or 0)
            limit = self.settings.brightness_limit
            pixels = tuple(scale(pixel, limit) for pixel in frame.pixels) if frame.pixels else None
            self.last_frame = LightingFrame(frame.color, frame.brightness * limit / 100, pixels, frame.done)
            return self.last_frame
