"""领域层：纯业务逻辑 + 业务异常。

- domain.py     : 领域逻辑（周期推进、状态推导、输入校验）——纯函数，无 IO
- exceptions.py : 业务异常体系（ApiError 及子类）
"""

from __future__ import annotations

from .domain import *  # noqa: F401, F403
from .exceptions import (
    ApiError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    PayloadTooLargeError,
    UnauthorizedError,
    ValidationError,
)

__all__ = [
    "ApiError",
    "ConflictError",
    "ForbiddenError",
    "NotFoundError",
    "PayloadTooLargeError",
    "UnauthorizedError",
    "ValidationError",
]
