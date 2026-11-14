"""Apply authenticated application snapshots without hosting CABEK application code.

Depends on the standalone lighting state and monotonic elapsed times; repeated
heartbeats preserve animation phases and never extend a completion deadline.
"""
from typing import Literal
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from lighting_api.lighting_routes import authorize
from lighting_api.lighting_state import timestamp

class ApplicationSnapshot(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    session_id: str = Field(min_length=1, max_length=128)
    sequence: int = Field(ge=0)
    state: Literal['BOOTING', 'INITIALIZING', 'READY', 'SCANNING', 'COMPLETED', 'OFF']
    ready: bool
    capture_id: str | None = Field(default=None, max_length=200)
    elapsed_ms: float = Field(default=0, ge=0, allow_inf_nan=False)
    warning: bool = False

    @model_validator(mode='after')
    def validate_capture(self):
        if (self.state == 'SCANNING') != bool(self.capture_id):
            raise ValueError('Only SCANNING requires an active capture identity')
        if self.state == 'READY' and not self.ready:
            raise ValueError('READY requires actual application readiness')
        return self

router = APIRouter(prefix='/api/v1/lights', dependencies=[Depends(authorize)])

@router.post('/events', status_code=202)
def application_event(payload: ApplicationSnapshot, request: Request):
    service = request.app.state.lighting
    with service.state.lock:
        previous = getattr(service, 'application_event', None)
        if previous and previous.session_id == payload.session_id and previous.sequence >= payload.sequence:
            return service.status()
        state = service.state
        changed = (previous is None or previous.session_id != payload.session_id or
                   (state.state, state.capture_id, state.warning) !=
                   (payload.state, payload.capture_id, payload.warning))
        if changed:
            state.state = payload.state
            state.capture_id = payload.capture_id
            state.warning = payload.warning
            state.entered_at = state.clock() - payload.elapsed_ms / 1000
            state.transitioned_at = timestamp()
            state.revision += 1
            state.test_color = state.test_deadline = None
            state.completion_deadline = state.entered_at + 10 if payload.state == 'COMPLETED' else None
        state.ready = payload.ready
        state.readiness_error = None if payload.ready else 'Application services are not ready.'
        service.application_event = payload
    return service.status()
