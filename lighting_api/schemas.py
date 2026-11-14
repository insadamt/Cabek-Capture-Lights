"""Define standalone HTTP errors without importing CABEK application schemas.

Depends on Pydantic and the existing lighting error envelope.
"""
from pydantic import BaseModel

class ErrorDetail(BaseModel):
    code: str
    message: str

class ErrorResponse(BaseModel):
    error: ErrorDetail
