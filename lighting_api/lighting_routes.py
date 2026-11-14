"""Expose ordinary lighting endpoints while preserving lifecycle arbitration.

Depends on the app-owned LightingService and existing structured error handlers;
manual previews cannot interrupt active capture.
"""

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from lighting_api.errors import DossierError
from lighting_api.schemas import ErrorResponse
from lighting_api.lighting_schemas import LightingStatus
from lighting_api.lighting_effects import EffectRequest, effect_catalog


class StateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal["BOOTING", "INITIALIZING", "READY", "SCANNING", "COMPLETED", "OFF"]


class StopRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    color: Literal["OFF", "RED", "BLUE", "GREEN", "WHITE"]


def require_enabled(request: Request):
    if not request.app.state.lighting.settings.enabled:
        raise DossierError(503, "lighting_disabled", "Lighting control is disabled.")


router = APIRouter(prefix="/api/v1/lights", tags=["Local lighting"],
                   dependencies=[Depends(require_enabled)], responses={
                       code: {"model": ErrorResponse} for code in (409, 422, 503)
                   })


@router.get("/status", response_model=LightingStatus)
def status(request: Request):
    return request.app.state.lighting.status()


@router.post("/state", status_code=202, response_model=LightingStatus)
def set_state(payload: StateRequest, request: Request):
    request.app.state.lighting.state.request_state(payload.state)
    return request.app.state.lighting.status()


@router.post("/test", status_code=202, response_model=LightingStatus)
def test_color(payload: TestRequest, request: Request):
    request.app.state.lighting.state.start_test(payload.color)
    return request.app.state.lighting.status()


@router.get("/capabilities")
def get_capabilities(request: Request):
    return {**request.app.state.lighting.driver.get_capabilities(), "can_preview": True}


@router.get("/effects")
def get_effects(request: Request):
    return effect_catalog(request.app.state.lighting.driver.get_capabilities())


@router.post("/effects", status_code=202, response_model=LightingStatus)
def start_effect(payload: EffectRequest, request: Request):
    service = request.app.state.lighting
    service.engine.start_preview(payload, service.driver.get_capabilities())
    return service.status()


@router.post("/stop", status_code=202, response_model=LightingStatus)
def stop_effect(request: Request, payload: StopRequest | None = None):
    request.app.state.lighting.engine.stop_preview()
    return request.app.state.lighting.status()
