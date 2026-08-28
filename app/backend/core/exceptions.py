"""业务自定义异常体系。

所有业务异常统一收敛为 ApiError 及其子类，由应用工厂注册的
全局 Error Handler 转译为 ``{code, message, data}`` 响应。
"""
from __future__ import annotations

from typing import Any


class ApiError(Exception):
    """业务异常基类。

    Attributes
    ----------
    message : str
        面向用户的中文提示（与既有文案保持一致）。
    status_code : int
        HTTP 状态码（默认 500）。
    code : int
        业务码，默认与 HTTP 状态码一致；前端按 code==0 判断成功。
    payload : dict | None
        附加数据（可选）。
    """

    status_code = 500
    code = 500

    def __init__(
        self,
        message: str | None = None,
        *,
        status_code: int | None = None,
        code: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message or self.message)
        self.message = message or self.message
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        self.payload = payload


class ValidationError(ApiError):
    """参数校验失败（400）。"""

    status_code = 400
    code = 400
    message = "请求参数错误"


class NotFoundError(ApiError):
    """资源不存在（404）。"""

    status_code = 404
    code = 404
    message = "资源不存在"


class ConflictError(ApiError):
    """状态冲突（409）：重名、数量上限等。"""

    status_code = 409
    code = 409
    message = "状态冲突"


class ForbiddenError(ApiError):
    """权限不足（403）。"""

    status_code = 403
    code = 403
    message = "权限不足"


class UnauthorizedError(ApiError):
    """身份缺失或非法（401）。"""

    status_code = 401
    code = 401
    message = "未认证"


class PayloadTooLargeError(ApiError):
    """请求体过大（413）。"""

    status_code = 413
    code = 413
    message = "请求体过大"
