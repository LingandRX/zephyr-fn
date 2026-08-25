#!/usr/bin/env python3
"""订阅管理 - HTTP API 服务（仅用 Python 标准库，零第三方依赖）。

监听方式：
  --uds <path>     Unix domain socket（飞牛统一网关 gatewaySocket 用）
  --http <port>    TCP 端口（本地开发/调试用）

在飞牛 fnOS 上由 cmd/main 拉起；网关校验登录态后把请求转发到
$TRIM_APPDEST/app.sock，并注入 X-Trim-Userid / X-Trim-Isadmin / X-Trim-Username。

API（与 zephyr-tarui 后端功能对齐）：
  订阅  GET/POST      /api/subscriptions
        GET/PUT/DELETE /api/subscriptions/{id}
        POST           /api/subscriptions/{id}/renew
  分类  GET/POST      /api/categories
        PUT/DELETE    /api/categories/{id}
  设置  GET/PUT       /api/settings
  统计  GET           /api/statistics?mode=nominal|actual
  日历  GET           /api/calendar?year=&month=
  备份  POST          /api/backup
        GET           /api/backup/export-json
        POST          /api/backup/import-json
        POST          /api/backup/import-csv
        GET           /api/backup/files
        DELETE        /api/backup/files?name=
        GET           /api/backup/files/download?name=
        GET           /api/export/csv
  通知  GET           /api/notifications/upcoming
  日志  GET           /api/logs/tail?lines=200
"""
from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import mimetypes
import os
import socket
import socketserver
import sys
import time
import urllib.parse
from dataclasses import dataclass
from datetime import date
from http import HTTPStatus
from pathlib import Path

try:  # 支持 python -m app.backend.server 与直接执行 server.py 两种方式。
    from . import backup, config, db, domain, email_sender, notifications, pushplus, scheduler, services
except ImportError:  # pragma: no cover - 直接从 backend 目录启动时使用。
    import backup
    import config
    import db
    import domain
    import email_sender
    import notifications
    import pushplus
    import scheduler
    import services

log = logging.getLogger(scheduler.LOGGER_NAME)


# 请求边界。该服务使用 socketserver 自己解析 HTTP，请求头和请求体都必须
# 在进入业务路由前限制大小，避免恶意客户端在解析阶段消耗无限内存。
MAX_REQUEST_LINE_BYTES = 8 * 1024
MAX_HEADER_LINE_BYTES = 8 * 1024
MAX_HEADER_BYTES = 32 * 1024
MAX_HEADER_COUNT = 64
MAX_REQUEST_BODY_BYTES = 5 * 1024 * 1024
MAX_USER_ID_LENGTH = 128


@dataclass(frozen=True)
class RequestIdentity:
    """网关认证后的请求身份。

    fnOS 统一网关会在完成登录校验后注入 X-Trim-Userid / X-Trim-Isadmin。
    本地 TCP 开发模式如果完全没有这两个请求头，则使用 local 管理员身份，
    保持直接访问 127.0.0.1 的开发流程可用；Unix Socket 模式必须由网关
    提供身份头。一旦请求显式携带身份头，就不再静默回退到管理员身份。
    """

    user_id: str
    is_admin: bool
    username: str | None = None
    is_local: bool = False


class AccessDeniedError(Exception):
    """请求身份无权访问目标资源。"""


_ADMIN_ONLY_PATHS = {
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


def _public_settings(settings: dict) -> dict:
    """返回可通过 HTTP 暴露的设置，绝不包含密钥原文。"""
    public = dict(settings)
    for field in _SECRET_SETTING_FIELDS:
        value = public.pop(field, None)
        configured = bool(value is not None and str(value).strip())
        public[f"{field}_configured"] = configured
        # 只下发星号掩码（个数与真实密钥长度一致），供前端“输入多少显示多少”隐藏显示
        public[f"{field}_masked"] = "*" * len(str(value)) if configured else ""
    return public


def _settings_update_payload(data: dict) -> dict:
    """过滤设置更新中的空值/掩码密钥，保持已有密钥。"""
    payload = dict(data)
    for field in _SECRET_SETTING_FIELDS:
        if field in payload and db.is_secret_placeholder(payload[field]):
            payload.pop(field, None)
    # configured 字段只是 GET 响应元数据，不能作为写入字段传给 db。
    payload.pop("smtp_password_configured", None)
    payload.pop("pushplus_token_configured", None)
    return payload


def _with_status(sub: dict) -> dict:
    sub = dict(sub)
    sub["status"] = domain.derive_status(sub.get("lifecycle", "active"), sub.get("next_due_date"))
    sub["status_label"] = domain.STATUS_LABELS.get(sub["status"], sub["status"])
    sub["status_color"] = domain.STATUS_COLORS.get(sub["status"], "#6B7280")
    return sub


# --------------------------------------------------------------------------- #
# 请求处理
# --------------------------------------------------------------------------- #

class Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        try:
            self._handle_request()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:  # noqa: BLE001
            log.exception("处理请求时出错")

    def _handle_request(self) -> None:
        request_line = self.rfile.readline(MAX_REQUEST_LINE_BYTES + 1)
        if not request_line:
            return
        if len(request_line) > MAX_REQUEST_LINE_BYTES or not request_line.endswith(b"\n"):
            self._error(HTTPStatus.REQUEST_URI_TOO_LONG, "请求行过长或格式不完整")
            return
        try:
            method, raw_target, proto = (
                request_line.decode("latin-1").rstrip("\r\n").split(" ", 2)
            )
        except ValueError:
            self._error(HTTPStatus.BAD_REQUEST, "请求行格式错误")
            return
        if not method or not raw_target or proto not in ("HTTP/1.0", "HTTP/1.1"):
            self._error(HTTPStatus.BAD_REQUEST, "请求行格式错误或 HTTP 版本不支持")
            return

        headers: dict[str, str] = {}
        header_bytes = len(request_line)
        header_count = 0
        while True:
            line = self.rfile.readline(MAX_HEADER_LINE_BYTES + 1)
            if not line:
                self._error(HTTPStatus.BAD_REQUEST, "请求头未完整结束")
                return
            header_bytes += len(line)
            if header_bytes > MAX_HEADER_BYTES:
                self._error(HTTPStatus.REQUEST_HEADER_FIELDS_TOO_LARGE, "请求头总大小超过限制")
                return
            if len(line) > MAX_HEADER_LINE_BYTES:
                self._error(HTTPStatus.REQUEST_HEADER_FIELDS_TOO_LARGE, "单个请求头过长")
                return
            if line in (b"\r\n", b"\n"):
                break
            if not line.endswith(b"\n"):
                self._error(HTTPStatus.BAD_REQUEST, "请求头格式不完整")
                return
            header_count += 1
            if header_count > MAX_HEADER_COUNT:
                self._error(HTTPStatus.REQUEST_HEADER_FIELDS_TOO_LARGE, "请求头数量超过限制")
                return
            if b":" not in line:
                self._error(HTTPStatus.BAD_REQUEST, "请求头格式错误")
                return
            name, _, value = line.decode("latin-1").partition(":")
            name = name.strip().lower()
            if not name or not self._valid_header_name(name):
                self._error(HTTPStatus.BAD_REQUEST, "请求头名称格式错误")
                return
            if name in headers:
                self._error(HTTPStatus.BAD_REQUEST, f"请求头重复: {name}")
                return
            headers[name] = value.strip()

        if headers.get("transfer-encoding"):
            self._error(HTTPStatus.NOT_IMPLEMENTED, "暂不支持 Transfer-Encoding，请使用 Content-Length")
            return

        raw_content_length = headers.get("content-length")
        if raw_content_length is None:
            content_length = 0
        elif not raw_content_length or not raw_content_length.isascii() or not raw_content_length.isdigit():
            self._error(HTTPStatus.BAD_REQUEST, "Content-Length 必须为非负整数")
            return
        else:
            content_length = int(raw_content_length)
        if content_length > MAX_REQUEST_BODY_BYTES:
            self._error(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                f"请求体过大，不能超过 {MAX_REQUEST_BODY_BYTES} 字节",
            )
            return

        body = self.rfile.read(content_length) if content_length > 0 else b""
        if len(body) != content_length:
            self._error(HTTPStatus.BAD_REQUEST, "请求体未完整接收")
            return

        self._route(method, raw_target, headers, body)

    @staticmethod
    def _valid_header_name(name: str) -> bool:
        # RFC 7230 token 字符；拒绝控制字符和带空格的伪请求头。
        token_chars = "!#$%&'*+-.^_`|~"
        return name.isascii() and all(char.isalnum() or char in token_chars for char in name)

    @staticmethod
    def _parse_admin_flag(raw_value: str | None) -> bool:
        if raw_value is None:
            return False
        value = raw_value.strip().lower()
        if value in {"1", "true", "yes", "on"}:
            return True
        if value in {"", "0", "false", "no", "off"}:
            return False
        raise ValueError("X-Trim-Isadmin 必须为 true/false")

    def _parse_identity(self, headers: dict[str, str]) -> RequestIdentity:
        """统一解析网关身份，并仅在本地 TCP 模式保留无头回退。"""
        raw_user_id = headers.get("x-trim-userid")
        raw_is_admin = headers.get("x-trim-isadmin")
        raw_username = headers.get("x-trim-username")

        if raw_user_id is None and raw_is_admin is None:
            if not getattr(self.server, "allow_headerless_local_identity", False):
                raise ValueError("Unix Socket 模式必须携带 X-Trim-Userid 身份头")
            return RequestIdentity(
                user_id="local",
                is_admin=True,
                username=raw_username or "local",
                is_local=True,
            )
        if raw_user_id is None:
            raise ValueError("缺少 X-Trim-Userid，无法确定请求用户")

        user_id = raw_user_id.strip()
        if not user_id:
            raise ValueError("X-Trim-Userid 不能为空")
        if len(user_id) > MAX_USER_ID_LENGTH:
            raise ValueError(f"X-Trim-Userid 不能超过 {MAX_USER_ID_LENGTH} 个字符")
        if any(ord(char) < 0x20 or ord(char) == 0x7F for char in user_id):
            raise ValueError("X-Trim-Userid 含有非法控制字符")

        username = raw_username.strip() if raw_username else None
        if username and any(ord(char) < 0x20 or ord(char) == 0x7F for char in username):
            raise ValueError("X-Trim-Username 含有非法控制字符")

        return RequestIdentity(
            user_id=user_id,
            is_admin=self._parse_admin_flag(raw_is_admin),
            username=username,
            is_local=False,
        )

    # ----- 路由 -----

    def _route(self, method: str, raw_target: str, headers: dict, body: bytes) -> None:
        try:
            parsed = urllib.parse.urlsplit(raw_target)
            path = self._normalize_path(parsed.path)
            query = urllib.parse.parse_qs(parsed.query)
            identity = self._parse_identity(headers)

            # 设置、全量备份和全量导出使用的是全局数据访问函数，不能让普通
            # 用户通过这些接口读取或修改其他用户的数据。导入接口仍按
            # identity.user_id 处理，保持现有的用户级导入能力。
            protected_resource = _ADMIN_ONLY_PATHS.get(path)
            if protected_resource:
                self._require_admin(identity, protected_resource)

            # 挂载路径不带结尾斜杠时 302 跳转，避免相对资源（style.css/app.js）
            # 解析到上一层目录（/app/...）导致网关 404。
            if not parsed.path.endswith("/") and path == "/":
                self._redirect(parsed.path + "/")
                return

            user_id = identity.user_id
            # 新用户首次访问 API 时补种默认分类（幂等，见 db.ensure_default_categories_for_user）。
            if path.startswith("/api/"):
                db.ensure_default_categories_for_user(user_id)
            if path == "/api/subscriptions" and method == "GET":
                self._json([_with_status(s) for s in db.get_all_subscriptions(user_id)])
            elif path == "/api/subscriptions" and method == "POST":
                self._json(_with_status(db.create_subscription(user_id, self._json_body(body))),
                           HTTPStatus.CREATED)
            elif path == "/api/categories" and method == "GET":
                self._json(db.get_all_categories(user_id))
            elif path == "/api/categories" and method == "POST":
                try:
                    cat = db.create_category(user_id, self._json_body(body))
                except ValueError as exc:
                    msg = str(exc)
                    if "已存在" in msg or "已达上限" in msg:
                        self._json({"error": msg}, HTTPStatus.CONFLICT)
                        return
                    raise
                self._json(cat, HTTPStatus.CREATED)
            elif path == "/api/settings" and method == "GET":
                self._json(_public_settings(db.get_app_settings()))
            elif path == "/api/settings" and method == "PUT":
                payload = _settings_update_payload(self._json_body(body))
                self._json(_public_settings(db.update_app_settings(payload)))
            elif path == "/api/statistics" and method == "GET":
                mode = (query.get("mode") or ["nominal"])[0]
                self._json(services.calculate_statistics(user_id, mode))
            elif path == "/api/calendar" and method == "GET":
                year = int((query.get("year") or [date.today().year])[0])
                month = int((query.get("month") or [date.today().month])[0])
                self._json(services.get_calendar_events(user_id, year, month))
            elif path == "/api/backup" and method == "POST":
                self._json(scheduler.backup_now(include_all=True))
            elif path == "/api/backup/export-json" and method == "GET":
                self._raw_text(backup.export_json_string(include_all=True), "application/json; charset=utf-8")
            elif path == "/api/backup/import-json" and method == "POST":
                result = backup.import_from_json(body.decode("utf-8"), user_id)
                self._json(result)
            elif path == "/api/backup/import-csv" and method == "POST":
                result = backup.import_from_csv(body.decode("utf-8"), user_id)
                self._json(result)
            elif path == "/api/backup/files" and method == "GET":
                self._json(_list_backup_files())
            elif path == "/api/backup/files" and method == "DELETE":
                ok = _delete_backup_file((query.get("name") or [""])[0])
                self._json({"ok": ok}, HTTPStatus.OK if ok else HTTPStatus.NOT_FOUND)
            elif path == "/api/backup/files/download" and method == "GET":
                file_path = _resolve_backup_file((query.get("name") or [""])[0])
                if not file_path.is_file():
                    self._json({"error": "备份文件不存在"}, HTTPStatus.NOT_FOUND)
                    return
                self._raw(
                    HTTPStatus.OK, "application/octet-stream", file_path.read_bytes(),
                    content_disposition=f'attachment; filename="{file_path.name}"',
                )
            elif path == "/api/export/csv" and method == "GET":
                self._raw_text(backup.export_csv(include_all=True), "text/csv; charset=utf-8")
            elif path == "/api/notifications/upcoming" and method == "GET":
                self._json(_upcoming_notifications(user_id))
            elif path == "/api/logs/tail" and method == "GET":
                # 系统级日志尾读（不区分用户；多用户场景下如需隔离可后续按 user 过滤）
                try:
                    want = min(int((query.get("lines") or ["200"])[0]), 1000)
                except ValueError:
                    want = 200
                self._json(_read_log_tail(config.logs_dir() / "app.log", want))
            elif path == "/api/notifications/test-email" and method == "POST":
                self._test_email(body)
            elif path == "/api/notifications/test-pushplus" and method == "POST":
                self._test_pushplus(body)
            elif path.startswith("/api/subscriptions/"):
                self._route_subscription(method, path, user_id, body)
            elif path.startswith("/api/categories/"):
                self._route_category(method, path, user_id, body)
            else:
                self._serve_static(path)
        except AccessDeniedError as exc:
            self._json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
        except ValueError as exc:
            msg = str(exc)
            if "已存在" in msg or "已达上限" in msg:
                self._json({"error": msg}, HTTPStatus.CONFLICT)
            else:
                self._json({"error": msg}, HTTPStatus.BAD_REQUEST)
        except Exception:  # noqa: BLE001
            log.exception("API 处理失败: %s %s", method, raw_target)
            self._json({"error": "服务器内部错误"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    @staticmethod
    def _require_admin(identity: RequestIdentity, resource: str) -> None:
        if not identity.is_admin:
            raise AccessDeniedError(f"仅管理员可访问{resource}")

    def _route_subscription(self, method: str, path: str, user_id: str, body: bytes) -> None:
        parts = path[len("/api/subscriptions/"):].split("/")
        sub_id = parts[0] if parts else ""
        action = parts[1] if len(parts) > 1 else None

        if action == "renew" and method == "POST":
            sub = db.renew_subscription(sub_id, user_id)
        elif action is None and method == "GET":
            sub = db.get_subscription_by_id(sub_id, user_id)
        elif action is None and method == "PUT":
            sub = db.update_subscription(sub_id, user_id, self._json_body(body))
        elif action is None and method == "DELETE":
            ok = db.delete_subscription(sub_id, user_id)
            self._json({"ok": ok}, HTTPStatus.OK if ok else HTTPStatus.NOT_FOUND)
            return
        else:
            self._json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
            return

        if sub is None:
            self._json({"error": "订阅不存在"}, HTTPStatus.NOT_FOUND)
        else:
            self._json(_with_status(sub))

    def _route_category(self, method: str, path: str, user_id: str, body: bytes) -> None:
        cat_id = path[len("/api/categories/"):].rstrip("/")
        if method == "PUT":
            try:
                cat = db.update_category(cat_id, user_id, self._json_body(body))
            except ValueError as exc:
                msg = str(exc)
                if "已存在" in msg or "已达上限" in msg:
                    self._json({"error": msg}, HTTPStatus.CONFLICT)
                    return
                raise
        elif method == "DELETE":
            ok = db.delete_category(cat_id, user_id)
            self._json({"ok": ok}, HTTPStatus.OK if ok else HTTPStatus.NOT_FOUND)
            return
        else:
            self._json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
            return
        if cat is None:
            self._json({"error": "分类不存在"}, HTTPStatus.NOT_FOUND)
        else:
            self._json(cat)

    # ----- 网关路径归一化 -----

    def _normalize_path(self, path: str) -> str:
        """统一网关会把 gatewayPrefix 原样转发给应用（文档：GET /app/myapp/list）。

        这里剥离前缀，使 /app/subscription/... 与本地直接访问 / 等价：
        1. 优先按配置的 GATEWAY_PREFIX (/app/subscription) 剥离；
        2. 若真机上注册的前缀与配置不一致（例如配成了 /app），
           则从 /app/ 之后取路径，并校验其为 API 或存在的静态文件后使用。
        """
        prefix = config.gateway_prefix()
        if path == prefix:
            return "/"
        if path.startswith(prefix + "/"):
            return path[len(prefix):] or "/"
        if path == "/app":
            return "/"
        if path.startswith("/app/"):
            candidate = "/" + path[len("/app/"):]
            if self._is_internal_path(candidate):
                return candidate
        return path

    def _is_internal_path(self, path: str) -> bool:
        """判断剥离候选前缀后的路径是否确实是本应用内部路径（API 或静态文件）。"""
        if path == "/" or path.startswith("/api/"):
            return True
        root = config.www_dir().resolve()
        rel = path.lstrip("/")
        if not rel:
            return True
        target = (root / rel).resolve()
        return self._is_path_within(root, target) and target.is_file()

    # ----- 测试通知 -----

    def _test_email(self, body: bytes) -> None:
        payload = self._json_body(body)
        settings = db.get_app_settings()

        host = payload.get("smtp_host") or settings.get("smtp_host")
        if not host:
            raise ValueError("请先填写或配置 SMTP 服务器")

        port = payload.get("smtp_port") or settings.get("smtp_port") or 465
        username = payload.get("smtp_username") or settings.get("smtp_username")
        from_address = (
            payload.get("smtp_from_address")
            or settings.get("smtp_from_address")
            or username
        )

        password_draft = payload.get("smtp_password")
        if password_draft and not db.is_secret_placeholder(password_draft):
            password = password_draft
        else:
            password = settings.get("smtp_password")

        to_address = (
            payload.get("to_address")
            or payload.get("smtp_to_address")
            or from_address
            or username
        )
        if not to_address:
            raise ValueError("请提供测试接收邮箱（或配置发件人/用户名）")

        subject = "【订阅管理】邮件通知测试"
        content = (
            "这是一封来自订阅管理系统的测试邮件。\n\n"
            f"发送时间：{date.today().isoformat()}\n"
            "如果您看到这封邮件，说明您的 SMTP 邮件通知配置正确并已成功生效。"
        )

        try:
            email_sender.send_email(
                to_address=to_address,
                subject=subject,
                body=content,
                host=host,
                port=port,
                username=username,
                password=password,
                from_address=from_address,
            )
        except Exception as exc:
            self._json({"ok": False, "error": f"邮件发送失败: {exc}"}, HTTPStatus.BAD_REQUEST)
            return

        self._json({"ok": True, "message": f"测试邮件已发送至 {to_address}"})

    def _test_pushplus(self, body: bytes) -> None:
        payload = self._json_body(body)
        settings = db.get_app_settings()

        token_draft = payload.get("pushplus_token")
        if token_draft and not db.is_secret_placeholder(token_draft):
            token = token_draft
        else:
            token = settings.get("pushplus_token")

        if not token:
            raise ValueError("请先填写或配置 PushPlus Token")

        title = "【订阅管理】PushPlus 推送测试"
        content = (
            "<p>这是一条来自订阅管理系统的测试消息。</p>"
            f"<p>发送时间：{date.today().isoformat()}</p>"
            "<p>如果您看到此消息，说明您的 PushPlus 微信推送配置正确并已成功生效。</p>"
        )

        try:
            pushplus.send_pushplus(token=token, title=title, content=content)
        except Exception as exc:
            self._json({"ok": False, "error": f"PushPlus 发送失败: {exc}"}, HTTPStatus.BAD_REQUEST)
            return

        self._json({"ok": True, "message": "测试推送已发送成功"})

    # ----- 静态文件 -----

    _STATIC_MIME = {
        ".html": "text/html; charset=utf-8",
        ".htm": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".webp": "image/webp",
        ".ico": "image/x-icon",
        ".txt": "text/plain; charset=utf-8",
    }

    def _serve_static(self, path: str) -> None:
        root = config.www_dir().resolve()
        rel = path.lstrip("/") or "index.html"
        target = (root / rel).resolve()
        # 不能用字符串 startswith 判断目录边界：/www2 会错误地匹配 /www。
        # relative_to 同时能拒绝 ../ 越界路径和指向 root 外的符号链接。
        if not self._is_path_within(root, target) or not target.is_file():
            self._error(HTTPStatus.NOT_FOUND, "Not Found")
            return
        # MIME 显式映射（对齐官方 index.cgi 示例：css/js 带 charset；
        # .js 用 application/javascript），未知后缀回退 mimetypes 猜测。
        ctype = self._STATIC_MIME.get(target.suffix) \
            or mimetypes.guess_type(str(target))[0] \
            or "application/octet-stream"
        data = target.read_bytes()
        cache = rel != "index.html"
        self._raw(HTTPStatus.OK, ctype, data, cache=cache)

    @staticmethod
    def _is_path_within(root: Path, target: Path) -> bool:
        try:
            target.relative_to(root)
        except ValueError:
            return False
        return True

    # ----- 响应 -----

    def _redirect(self, location: str) -> None:
        body = b""
        head = (
            "HTTP/1.1 302 Found\r\n"
            f"Location: {location}\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n"
            "\r\n"
        )
        self.wfile.write(head.encode("latin-1"))
        self.wfile.flush()

    def _json(self, obj, status=HTTPStatus.OK) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._raw(status, "application/json; charset=utf-8", body)

    def _raw_text(self, text: str, ctype: str) -> None:
        self._raw(HTTPStatus.OK, ctype, text.encode("utf-8"))

    def _error(self, status, message: str) -> None:
        self._raw(status, "text/plain; charset=utf-8", message.encode("utf-8"))

    def _raw(self, status, ctype: str, body: bytes, cache: bool = False,
             content_disposition: str | None = None) -> None:
        code = int(status)
        phrase = HTTPStatus(code).phrase
        head = (
            f"HTTP/1.1 {code} {phrase}\r\n"
            f"Content-Type: {ctype}\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"{'Cache-Control: public, max-age=3600' if cache else 'Cache-Control: no-store'}\r\n"
            + (f"Content-Disposition: {content_disposition}\r\n" if content_disposition else "")
            + f"Connection: close\r\n"
            + "\r\n"
        )
        self.wfile.write(head.encode("latin-1"))
        self.wfile.write(body)
        self.wfile.flush()

    def _json_body(self, body: bytes) -> dict:
        if not body:
            return {}
        try:
            data = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("请求体不是合法 JSON") from exc
        if not isinstance(data, dict):
            raise ValueError("请求体应为 JSON 对象")
        return data


# --------------------------------------------------------------------------- #
# 辅助
# --------------------------------------------------------------------------- #

def _resolve_backup_file(name: str) -> Path:
    """把备份文件名解析为备份目录内的安全路径，防止路径穿越。

    只接受 basename 形式的文件名，且必须匹配备份列表使用的
    ``subscription-*`` 前缀；解析结果必须仍位于备份目录内。
    """
    filename = os.path.basename(str(name or "").strip())
    if not filename.startswith("subscription-") or filename == "subscription-":
        raise ValueError("非法的备份文件名")
    if filename in (".", "..") or "/" in filename or "\\" in filename:
        raise ValueError("非法的备份文件名")
    backup_dir = config.backup_dir().resolve()
    path = (backup_dir / filename).resolve()
    if path.parent != backup_dir:
        raise ValueError("非法的备份文件路径")
    return path


def _delete_backup_file(name: str) -> bool:
    path = _resolve_backup_file(name)
    if not path.is_file():
        return False
    path.unlink()
    return True


def _list_backup_files() -> list[dict]:
    backup_dir = config.backup_dir()
    if not backup_dir.exists():
        return []
    files = []
    for p in sorted(backup_dir.glob("subscription-*"), reverse=True)[:50]:
        files.append({
            "name": p.name,
            "size": p.stat().st_size,
            "modified": p.stat().st_mtime,
        })
    return files


def _upcoming_notifications(user_id: str) -> list[dict]:
    settings = db.get_app_settings()
    reminder_days = max(0, int(settings.get("notification_days") or 7))
    from datetime import timedelta
    today = date.today()
    end = today + timedelta(days=reminder_days)
    result = []
    for sub in db.get_all_subscriptions(user_id):
        if sub["lifecycle"] != "active" or not sub.get("next_due_date"):
            continue
        try:
            d = date.fromisoformat(sub["next_due_date"])
        except ValueError:
            continue
        if today <= d <= end:
            title, body = notifications.generate_notification_content(sub)
            result.append({
                "id": sub["id"],
                "name": sub["name"],
                "due_date": sub["next_due_date"],
                "days_until": (d - today).days,
                "amount": sub["amount"],
                "currency": sub["currency"],
                "title": title,
                "body": body,
            })
    result.sort(key=lambda x: x["days_until"])
    return result


# --------------------------------------------------------------------------- #
# 服务器类
# --------------------------------------------------------------------------- #

if hasattr(socketserver, "UnixStreamServer"):
    class ThreadingUnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
        daemon_threads = True
        allow_headerless_local_identity = False

        def server_bind(self) -> None:
            if os.path.exists(self.server_address):
                try:
                    os.unlink(self.server_address)
                except OSError:
                    pass
            super().server_bind()
else:
    # Windows 等平台没有 Unix domain socket 支持，Unix Socket 网关模式不可用
    ThreadingUnixServer = None  # type: ignore


class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True
    allow_headerless_local_identity = True


def _setup_logging(log_dir: Path, console: bool) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    # A：轮转日志 —— 单文件上限 2MB，保留 5 份（与备份保留策略对齐）
    handler = logging.handlers.RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=_LOG_MAX_BYTES,
        backupCount=_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(formatter)
    root = logging.getLogger(scheduler.LOGGER_NAME)
    # C：SUBSCRIPTION_DEBUG=1 时输出 DEBUG 级日志（默认 INFO）
    root.setLevel(logging.DEBUG if os.environ.get("SUBSCRIPTION_DEBUG") == "1" else logging.INFO)
    root.addHandler(handler)
    # B：仅本地 TCP 调试模式回显到终端；网关/真机只写 app.log，
    #    避免与 cmd/main 的 nohup 重定向（server.log）双写内容重复。
    if console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)
    _cleanup_old_logs(log_dir)


_LOG_RETENTION_DAYS = 30
_LOG_MAX_BYTES = 2 * 1024 * 1024
_LOG_BACKUP_COUNT = 5


def _cleanup_old_logs(log_dir: Path) -> None:
    """启动时清理超过保留期的轮转/历史日志文件（app.log.*、server.log.*）。"""
    try:
        cutoff = time.time() - _LOG_RETENTION_DAYS * 86400
        for p in log_dir.iterdir():
            try:
                if (
                    p.is_file()
                    and p.name.startswith(("app.log", "server.log"))
                    and p.stat().st_mtime < cutoff
                ):
                    p.unlink(missing_ok=True)
            except OSError:
                pass
    except OSError:
        pass


def _read_log_tail(log_path: Path, lines: int) -> dict:
    """C2：从文件尾部倒读最近 N 行日志（避免整读大文件）。"""
    if not log_path.is_file():
        return {"file": log_path.name, "lines": [], "error": None}
    try:
        with open(log_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = 8192
            tail = b""
            pos = size
            # 每次向前读一块，直到累计换行数超过目标行数或读到头
            while pos > 0:
                take = min(block, pos)
                pos -= take
                f.seek(pos)
                tail = f.read(take) + tail
                if tail.count(b"\n") > lines:
                    break
        text = tail.decode("utf-8", errors="replace")
        sliced = text.strip().splitlines()[-lines:]
        return {"file": log_path.name, "lines": sliced, "error": None}
    except OSError as exc:
        return {"file": log_path.name, "lines": [], "error": str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser(description="订阅管理 HTTP 服务")
    parser.add_argument("--uds", help="Unix domain socket 路径（网关模式）")
    parser.add_argument("--http", type=int, help="TCP 端口（本地调试）")
    parser.add_argument("--db", help="数据库文件路径")
    parser.add_argument("--www", help="前端静态目录")
    parser.add_argument("--share", help="备份目录")
    parser.add_argument("--init-db", action="store_true", help="仅初始化数据库后退出")
    parser.add_argument("--reminder-days", type=int,
                        help="安装向导提醒提前天数（配合 --init-db 使用）")
    args = parser.parse_args()

    config.override("DB_PATH", args.db)
    config.override("WWW_DIR", args.www)
    config.override("SHARE_DIR", args.share)
    if args.reminder_days is not None:
        config.override("wizard_reminder_days", str(args.reminder_days))

    db.connect(config.db_path())
    if args.init_db:
        print(f"数据库就绪: {config.db_path()}")
        return

    is_gateway = bool(args.uds or os.environ.get("TRIM_APPDEST"))
    _setup_logging(config.logs_dir(), console=not is_gateway)
    log.info("启动订阅管理 v%s (arch=%s)", config.app_version(), config.sys_arch())

    scheduler.start_scheduler()
    log.info("定时任务已启动 (备份目录 %s)", config.backup_dir())

    sock_path = args.uds
    if is_gateway:
        if ThreadingUnixServer is None:
            raise RuntimeError("Unix Socket 网关模式仅支持 Linux/macOS")
        sock_path = sock_path or str(Path(os.environ["TRIM_APPDEST"]) / "app.sock")
        server = ThreadingUnixServer(sock_path, Handler)
        log.info("监听统一网关 Unix Socket: %s", sock_path)
    else:
        port = args.http or 8000
        server = ThreadingTCPServer(("127.0.0.1", port), Handler)
        log.info("监听 http://127.0.0.1:%d", port)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("退出")
    finally:
        server.server_close()
        if ThreadingUnixServer is not None and isinstance(server, ThreadingUnixServer) and os.path.exists(sock_path):
            os.unlink(sock_path)


if __name__ == "__main__":
    main()
