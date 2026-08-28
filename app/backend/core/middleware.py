"""请求边界中间件：网关身份解析、管理员校验、默认分类补种、网关前缀剥离。

- 身份解析/权限校验/补种：普通 before_request 钩子，由应用工厂注册；
- 网关前缀剥离：必须在 Flask 创建 Request 之前改写 PATH_INFO，
  before_request 阶段修改 environ 对路由不生效，故实现为 WSGI 中间件。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flask import current_app, g, request

from .. import config
from ..core.exceptions import ForbiddenError, UnauthorizedError, ValidationError
from ..services.categories import ensure_default_categories_for_user


@dataclass(frozen=True)
class RequestIdentity:
    """网关认证后的请求身份。"""

    user_id: str
    is_admin: bool
    username: str | None = None
    is_local: bool = False


# 管理员专属路径
ADMIN_ONLY_PATHS = {
    "/api/settings": "系统设置",
    "/api/notifications/test-email": "测试邮件通知",
    "/api/notifications/test-pushplus": "测试 PushPlus 通知",
    "/api/backup": "全量备份",
    "/api/backup/export-json": "全量 JSON 导出",
    "/api/backup/files": "备份文件列表",
    "/api/backup/files/download": "备份文件下载",
    "/api/export/csv": "全量 CSV 导出",
}

_SECRET_SETTING_FIELDS = ("smtp_password", "pushplus_token")


def _parse_admin_flag(raw_value: str | None) -> bool:
    if raw_value is None:
        return False
    value = raw_value.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"", "0", "false", "no", "off"}:
        return False
    raise ValidationError("X-Trim-Isadmin 必须为 true/false")


def parse_identity() -> None:
    """解析网关身份，注入 ``g.identity``。"""
    raw_user_id = request.headers.get("X-Trim-Userid")
    raw_is_admin = request.headers.get("X-Trim-Isadmin")
    raw_username = request.headers.get("X-Trim-Username")

    if raw_user_id is None and raw_is_admin is None:
        if not current_app.config["ALLOW_HEADERLESS_LOCAL"]:
            raise UnauthorizedError("Unix Socket 模式必须携带 X-Trim-Userid 身份头")
        g.identity = RequestIdentity(
            user_id="local",
            is_admin=True,
            username=raw_username or "local",
            is_local=True,
        )
        return

    if raw_user_id is None:
        raise UnauthorizedError("缺少 X-Trim-Userid，无法确定请求用户")

    user_id = raw_user_id.strip()
    if not user_id:
        raise ValidationError("X-Trim-Userid 不能为空")
    if len(user_id) > config.MAX_USER_ID_LENGTH:
        raise ValidationError(f"X-Trim-Userid 不能超过 {config.MAX_USER_ID_LENGTH} 个字符")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in user_id):
        raise ValidationError("X-Trim-Userid 含有非法控制字符")

    username = raw_username.strip() if raw_username else None
    if username and any(ord(char) < 0x20 or ord(char) == 0x7F for char in username):
        raise ValidationError("X-Trim-Username 含有非法控制字符")

    is_admin = _parse_admin_flag(raw_is_admin)
    g.identity = RequestIdentity(
        user_id=user_id,
        is_admin=is_admin,
        username=username,
        is_local=False,
    )


def check_admin_only() -> None:
    """管理员专属路径权限校验。"""
    protected = ADMIN_ONLY_PATHS.get(request.path)
    if protected and not g.identity.is_admin:
        raise ForbiddenError(f"仅管理员可访问{protected}")


def ensure_default_categories() -> None:
    """新用户首次访问 API 时补种默认分类（幂等）。"""
    if request.path.startswith("/api/"):
        ensure_default_categories_for_user(g.identity.user_id)


def is_path_within(root: Path, target: Path) -> bool:
    try:
        target.relative_to(root)
    except ValueError:
        return False
    return True


class GatewayPrefixMiddleware:
    """WSGI 层网关前缀剥离。

    统一网关会把 gatewayPrefix 原样转发给应用（如 /app/subscription/api/x），
    本中间件在 Flask 处理请求之前改写 PATH_INFO / SCRIPT_NAME，
    使 /app/subscription/... 与本地直接访问 / 等价。
    """

    def __init__(self, wsgi_app: Any, prefix: str, www_dir: Path) -> None:
        self.wsgi_app = wsgi_app
        self.prefix = prefix
        self.www_dir = www_dir

    def _is_internal_path(self, path: str) -> bool:
        """判断剥离候选前缀后的路径是否确实是本应用内部路径。"""
        if path == "/" or path.startswith("/api/"):
            return True
        root = self.www_dir.resolve()
        rel = path.lstrip("/")
        if not rel:
            return True
        target = (root / rel).resolve()
        return is_path_within(root, target) and target.is_file()

    def __call__(self, environ: dict, start_response) -> Any:
        path = environ.get("PATH_INFO") or "/"
        prefix = self.prefix

        if path == prefix or path == prefix + "/":
            environ["PATH_INFO"] = "/"
            environ["SCRIPT_NAME"] = (environ.get("SCRIPT_NAME") or "") + prefix
        elif path.startswith(prefix + "/"):
            environ["PATH_INFO"] = path[len(prefix):]
            environ["SCRIPT_NAME"] = (environ.get("SCRIPT_NAME") or "") + prefix
        elif path == "/app":
            environ["PATH_INFO"] = "/"
        elif path.startswith("/app/"):
            candidate = "/" + path[len("/app/"):]
            if self._is_internal_path(candidate):
                environ["PATH_INFO"] = candidate
                environ["SCRIPT_NAME"] = (environ.get("SCRIPT_NAME") or "") + "/app"

        return self.wsgi_app(environ, start_response)
