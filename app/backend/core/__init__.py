"""核心层：纯领域逻辑 + 公共基础设施。

- domain.py     : 领域逻辑（周期推进、状态派生、输入校验）——纯函数，无 IO
- exceptions.py : 业务异常体系（ApiError 及子类）
- response.py   : 统一响应结构 {code, message, data}
- middleware.py : 请求边界中间件（身份解析、权限校验、网关前缀剥离）
"""
from __future__ import annotations

from . import domain
from .exceptions import (
    ApiError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    PayloadTooLargeError,
    UnauthorizedError,
    ValidationError,
)
from .response import error, ok

__all__ = [
    "ApiError",
    "ConflictError",
    "ForbiddenError",
    "NotFoundError",
    "PayloadTooLargeError",
    "UnauthorizedError",
    "ValidationError",
    "domain",
    "error",
    "ok",
]
