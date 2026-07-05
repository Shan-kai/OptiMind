"""统一异常与全局异常处理。所有业务错误以 OptiMindError 为根，避免抛出裸 Exception。"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class OptiMindError(Exception):
    """所有 OptiMind 业务异常的基类。"""

    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class ValidationError(OptiMindError):
    """IR / Instance 校验失败。"""

    def __init__(self, message: str) -> None:
        super().__init__("validation_error", message, status_code=422)


class SolverError(OptiMindError):
    """求解器层错误（不可行、超时、内存溢出等）。"""

    def __init__(self, message: str) -> None:
        super().__init__("solver_error", message, status_code=502)


class ConfigurationError(OptiMindError):
    """配置错误（缺少必填项、非法配置值等）。"""

    def __init__(self, message: str) -> None:
        super().__init__("configuration_error", message, status_code=400)


class NotFoundError(OptiMindError):
    """请求的资源不存在。"""

    def __init__(self, message: str) -> None:
        super().__init__("not_found", message, status_code=404)


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器，统一错误响应格式。"""

    @app.exception_handler(OptiMindError)
    async def _handle_optimind_error(_: Request, exc: OptiMindError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message},
        )
