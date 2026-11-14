"""Define the public distinction between desired lighting and acknowledged hardware.

Depends on Pydantic; nullable historical fields remain available during a USB outage
without implying that the unavailable ESP32 still has the same output.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


LightingColor = Literal["OFF", "RED", "BLUE", "GREEN", "WHITE"]


class SuccessfulCommand(BaseModel):
    command: str
    color: str
    acknowledged_at: datetime


class LightingStatus(BaseModel):
    state: Literal["BOOTING", "INITIALIZING", "READY", "SCANNING", "COMPLETED", "OFF"]
    color: str
    rgb: tuple[int, int, int]
    ready: bool
    readiness_error: str | None
    active_capture_id: str | None
    test_active: bool
    last_transition_at: datetime
    enabled: bool
    connection_status: Literal["connected", "disconnected", "disabled"]
    esp32_available: bool
    synchronized: bool
    acknowledged_color: str | None
    firmware: dict[str, str] | None
    last_successful_command: SuccessfulCommand | None
    last_error: str | None
    last_seen_at: datetime | None
    brightness: float
    active_effect: str | None
    preview_active: bool
    requested_effect: dict | None
    simulated: bool
    pixels: tuple[tuple[int, int, int], ...] | None
    acknowledged_rgb: tuple[int, int, int] | None
    capability_error: str | None
