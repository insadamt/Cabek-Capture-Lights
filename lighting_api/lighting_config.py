"""Load the small serial/rendering configuration for the independent controller.

Depends on environment variables and python-dotenv; no application state is read.
"""
from dataclasses import dataclass
import math
import os
from pathlib import Path


@dataclass(frozen=True)
class LightingSettings:
    port: str = "auto"
    baud: int = 115200
    timeout: float = 1.0
    reconnect_seconds: float = 2.0
    health_seconds: float = 5.0
    update_hz: float = 15.0

    def __post_init__(self):
        intervals = (self.timeout, self.reconnect_seconds, self.health_seconds)
        if not self.port or self.baud <= 0 or not all(math.isfinite(v) and 0 < v <= 60 for v in intervals):
            raise ValueError("Configure a serial port, positive baud and intervals up to 60 seconds.")
        if not math.isfinite(self.update_hz) or not 1 <= self.update_hz <= 20:
            raise ValueError("Update rate must be 1–20 Hz.")

    @classmethod
    def from_environment(cls):
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=False)
        return cls(
            port=os.getenv("CABEK_LIGHTS_PORT", "auto"),
            baud=int(os.getenv("CABEK_LIGHTS_BAUD", "115200")),
            timeout=float(os.getenv("CABEK_LIGHTS_TIMEOUT", "1")),
            reconnect_seconds=float(os.getenv("CABEK_LIGHTS_RECONNECT_SECONDS", "2")),
            health_seconds=float(os.getenv("CABEK_LIGHTS_HEALTH_SECONDS", "5")),
            update_hz=float(os.getenv("CABEK_LIGHTS_UPDATE_HZ", "15")),
        )
