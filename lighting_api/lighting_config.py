"""Configure the optional local lighting owner and bounded effect rendering.

Depends on environment configuration and validated hardware/rendering limits.
"""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class LightingSettings:
    enabled: bool = False
    port: str = "auto"
    baud: int = 115200
    timeout: float = 1.0
    reconnect_seconds: float = 2.0
    health_seconds: float = 5.0
    driver: str = "dmx_rgb"
    update_hz: float = 15
    preview_seconds: float = 30
    brightness_limit: float = 100
    pixel_count: int = 60
    pixel_mapping: tuple[int, ...] = ()
    color_order: str = "RGB"

    def __post_init__(self):
        if self.baud <= 0 or not all(0 < value <= 60 for value in (
            self.timeout, self.reconnect_seconds, self.health_seconds,
        )):
            raise ValueError("Lighting baud and bounded time intervals must be positive.")
        if self.driver not in ("dmx_rgb", "simulated_pixels"):
            raise ValueError("Only verified DMX RGB or explicit pixel simulation is available.")
        if not 1 <= self.update_hz <= 20 or not 1 <= self.preview_seconds <= 120:
            raise ValueError("Update rate must be 1–20 Hz and preview timeout 1–120 seconds.")
        if not 0 <= self.brightness_limit <= 100 or not 1 <= self.pixel_count <= 1024:
            raise ValueError("Brightness limit must be 0–100 and zone count 1–1024.")
        if sorted(self.color_order) != list("BGR"):
            raise ValueError("Color order must be a permutation of RGB.")
        if self.pixel_mapping and sorted(self.pixel_mapping) != list(range(self.pixel_count)):
            raise ValueError("Zone mapping must be a permutation of all logical zone indices.")

    @classmethod
    def from_environment(cls):
        from dotenv import load_dotenv
        from pathlib import Path
        load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=False)
        return cls(
            driver=os.getenv("CABEK_LIGHTS_DRIVER", "dmx_rgb"),
            update_hz=float(os.getenv("CABEK_LIGHTS_UPDATE_HZ", "15")),
            preview_seconds=float(os.getenv("CABEK_LIGHTS_PREVIEW_SECONDS", "30")),
            brightness_limit=float(os.getenv("CABEK_LIGHTS_BRIGHTNESS_LIMIT", "100")),
            pixel_count=int(os.getenv("CABEK_LIGHTS_PIXEL_COUNT", "60")),
            pixel_mapping=tuple(int(part) for part in os.getenv("CABEK_LIGHTS_PIXEL_MAPPING", "").split(",") if part),
            color_order=os.getenv("CABEK_LIGHTS_COLOR_ORDER", "RGB"),
            enabled=os.getenv("CABEK_LIGHTS_ENABLED", "0") == "1",
            port=os.getenv("CABEK_LIGHTS_PORT", "auto"),
            baud=int(os.getenv("CABEK_LIGHTS_BAUD", "115200")),
            timeout=float(os.getenv("CABEK_LIGHTS_TIMEOUT", "1")),
            reconnect_seconds=float(os.getenv("CABEK_LIGHTS_RECONNECT_SECONDS", "2")),
            health_seconds=float(os.getenv("CABEK_LIGHTS_HEALTH_SECONDS", "5")),
        )
