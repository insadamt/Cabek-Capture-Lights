"""Serve the lighting API from this firmware repository as an independent process.

Depends on FastAPI, local settings and one serial owner. Application lifecycle
snapshots arrive over HTTP; no CABEK or AutoEstimate package is imported.
"""
import asyncio
from contextlib import asynccontextmanager
import os
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException
from lighting_api.errors import DossierError, handle_dossier_error, handle_validation_error, handle_http_error
from lighting_api.lighting_config import LightingSettings
from lighting_api.lighting_service import LightingService
from lighting_api.lighting_routes import router
from lighting_api.events import router as event_router

def create_app(settings=None, service=None):
    service = service or LightingService(settings or LightingSettings.from_environment())
    @asynccontextmanager
    async def lifespan(app):
        service.start()
        try:
            yield
        finally:
            await asyncio.to_thread(service.close)
    app = FastAPI(title='CABEK ESP32 Lighting API', version='1.0.0', lifespan=lifespan)
    app.state.lighting = service
    app.add_exception_handler(DossierError, handle_dossier_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(HTTPException, handle_http_error)
    origins = [item.strip() for item in os.getenv('CABEK_LIGHTS_CORS_ORIGINS', '').split(',') if item.strip()]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=['GET','POST'],
                           allow_headers=['Authorization','Content-Type'])
    app.include_router(router)
    app.include_router(event_router)
    return app
