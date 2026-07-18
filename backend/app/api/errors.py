from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers


def error_response(error: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={
            "error": {
                "code": error.code,
                "message": error.message,
                "details": error.details,
            }
        },
        headers=error.headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, error: AppError) -> JSONResponse:
        return error_response(error)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, error: RequestValidationError
    ) -> JSONResponse:
        fields = [
            {
                "path": ".".join(str(part) for part in item["loc"]),
                "reason": item["msg"],
            }
            for item in error.errors()
        ]
        return error_response(
            AppError(
                422,
                "VALIDATION_ERROR",
                "Request validation failed",
                {"fields": fields},
            )
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        _request: Request, error: StarletteHTTPException
    ) -> JSONResponse:
        code = "NOT_FOUND" if error.status_code == 404 else "HTTP_ERROR"
        return error_response(AppError(error.status_code, code, str(error.detail)))

    @app.exception_handler(Exception)
    async def handle_internal_error(_request: Request, _error: Exception) -> JSONResponse:
        return error_response(AppError(500, "INTERNAL_ERROR", "Internal server error"))
