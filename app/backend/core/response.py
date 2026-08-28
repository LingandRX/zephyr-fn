"""统一接口响应结构：``{code, message, data}``。

- code == 0 表示成功；非 0 为业务/错误码（默认与 HTTP 状态码一致）。
- 错误响应由全局 Error Handler 统一生成，业务代码只负责抛异常。
"""
from __future__ import annotations

from typing import Any

from flask import jsonify, Response


def ok(data: Any = None, message: str = "ok", code: int = 0) -> Response:
    """成功响应。"""
    return jsonify({"code": code, "message": message, "data": data})


def error(message: str, code: int, status_code: int | None = None) -> Response:
    """显式错误响应（供 Error Handler 及极少数直出场景使用）。"""
    return jsonify({"code": code, "message": message, "data": None}), status_code or code
