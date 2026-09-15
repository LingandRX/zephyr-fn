"""HTTP 基础设施层。

- middleware.py : 请求边界中间件（身份解析、权限校验、网关前缀剥离）
- response.py   : 统一响应结构 {code, message, data}
"""

from __future__ import annotations

from .middleware import (
    GatewayPrefixMiddleware,
    RequestIdentity,
    check_admin_only,
    ensure_default_categories,
    is_path_within,
    parse_identity,
)
from .response import error, ok

__all__ = [
    "GatewayPrefixMiddleware",
    "RequestIdentity",
    "check_admin_only",
    "ensure_default_categories",
    "error",
    "is_path_within",
    "ok",
    "parse_identity",
]
