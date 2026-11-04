"""统一业务异常(v8)。

API 层统一在 main.py 注册 handler,输出一致结构:{code, message}。
不泄露 SQL/堆栈/路径/密钥(内部细节只进日志)。
"""
from typing import Any


class AppError(Exception):
    """业务异常基类。status_code 供 API 层映射 HTTP 状态。"""
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str = "", *, detail: Any = None):
        super().__init__(message or self.code)
        self.message = message or self.code
        self.detail = detail


class NotFoundError(AppError):
    """资源不存在或无权访问(不泄漏存在性,统一 404)。"""
    status_code = 404
    code = "not_found"


class PermissionDeniedError(AppError):
    status_code = 403
    code = "permission_denied"


class ConflictError(AppError):
    """状态冲突(如 KB 仍被挂载时删除)。"""
    status_code = 409
    code = "conflict"


class ValidationError(AppError):
    status_code = 400
    code = "validation_error"
