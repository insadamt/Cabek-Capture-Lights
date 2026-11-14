"""Return concise lighting failures with useful HTTP codes and no raw payloads.

Depends on FastAPI exception handling; shared by serial, effects and routes.
"""
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


class LightingError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def error_response(status_code, code, message):
    return JSONResponse(status_code=status_code, content={
        'success': False, 'error': {'code': code, 'message': message},
    })


def handle_lighting_error(request: Request, error: LightingError):
    return error_response(error.status_code, error.code, error.message)


def handle_validation_error(request: Request, error: RequestValidationError):
    return error_response(422, 'invalid_request', 'Invalid parameters for the selected effect.')


def handle_http_error(request: Request, error: HTTPException):
    response = error_response(error.status_code, 'http_error', 'Request could not be served.')
    if error.headers:
        response.headers.update(error.headers)
    return response
