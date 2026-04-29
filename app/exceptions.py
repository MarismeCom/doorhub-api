from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppException(Exception):
    def __init__(self, code: int, message: str, status_code: int = 400, detail: str | None = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail
        super().__init__(message)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    payload = {"code": exc.code, "message": exc.message}
    if exc.detail:
        payload["detail"] = exc.detail
    return JSONResponse(status_code=exc.status_code, content=payload)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppException, app_exception_handler)
