"""Preserve safe HTTP errors without exposing credentials or submitted values.

Depends on FastAPI and the standalone lighting error envelope.
"""
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


# ============================================================
# ERROR CONTRACT
# ============================================================

class DossierError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


# ============================================================
# SAFE HTTP ERROR RESPONSES
# ============================================================

def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def handle_dossier_error(request: Request, error: DossierError) -> JSONResponse:
    return error_response(error.status_code, error.code, error.message)


def handle_validation_error(
    request: Request, error: RequestValidationError
) -> JSONResponse:

    # Validation details can contain submitted values; expose a stable message instead.

    return error_response(422, "invalid_request", "Invalid request parameters.")


def handle_http_error(request: Request, error: HTTPException) -> JSONResponse:
    response = error_response(error.status_code, "http_error", "Request could not be served.")
    if error.headers:
        response.headers.update(error.headers)
    return response
