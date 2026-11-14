"""Host two local lighting routes and start one independent animation worker.

Depends on FastAPI, settings and LightingService; imports no CABEK application.
"""
import asyncio
from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException

from lighting_api.errors import LightingError, handle_lighting_error, handle_validation_error, handle_http_error
from lighting_api.lighting_config import LightingSettings
from lighting_api.lighting_routes import router
from lighting_api.lighting_service import LightingService


def create_app(settings=None, service=None):
    service = service or LightingService(settings or LightingSettings.from_environment())

    @asynccontextmanager
    async def lifespan(app):
        service.start()
        try:
            yield
        finally:
            await asyncio.to_thread(service.close)

    app = FastAPI(title='CABEK Lighting API', version='2.0.0', lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.lighting = service
    app.add_exception_handler(LightingError, handle_lighting_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(HTTPException, handle_http_error)
    origins = [item.strip() for item in os.getenv('CABEK_LIGHTS_CORS_ORIGINS', '').split(',') if item.strip()]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=['POST'],
                           allow_headers=['Content-Type'])
    app.include_router(router)
    return app
