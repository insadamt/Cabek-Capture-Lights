"""Expose only set and off operations, independently of CABEK AI.

Depends on FastAPI, EffectRequest and the single worker stored on the app.
"""
from fastapi import APIRouter, Request, Response

from lighting_api.lighting_effects import EffectRequest

router = APIRouter(prefix='/api/lights', tags=['Lighting'])


@router.post('/set')
def set_lights(payload: EffectRequest, request: Request, response: Response):
    result = request.app.state.lighting.set_effect(payload)
    response.status_code = 200 if payload.effect == 'solid' else 202
    return result


@router.post('/off')
def off(request: Request):
    return request.app.state.lighting.off()
