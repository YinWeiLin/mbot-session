from typing import Any
from pydantic import BaseModel


class ApiResponse(BaseModel):
    success: bool
    data: Any = None
    error: str = None


def ok(data: Any = None) -> ApiResponse:
    return ApiResponse(success=True, data=data)


def fail(error: str) -> ApiResponse:
    return ApiResponse(success=False, error=error)
