#!/usr/bin/env python3
"""订阅管理 - HTTP API 服务（Flask 版本）。

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
import os
import socket
import sys
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from flask import Flask, Response, g, jsonify, redirect, request, send_file

try:
    from . import config
    from .core import domain
    from .services import backup, notifications, scheduler, statistics
    from .storage import db
    from .utils.channels import email as email_sender, pushplus
except ImportError:
    import config
    from core import domain
    from services import backup, notifications, scheduler, statistics
    from storage import db
    from utils.channels import email as email_sender, pushplus

log = logging.getLogger(scheduler.LOGGER_NAME)

# --------------------------------------------------------------------------- #
# 请求边界
# --------------------------------------------------------------------------- #
MAX_REQUEST_BODY_BYTES = 5 * 1024 * 1024
MAX_USER_ID_LENGTH = 128


@dataclass(frozen=True)
class RequestIdentity:
    """网关认证后的请求身份。"""
    user_id: str
    is_admin: bool
    username: str | None = None
    is_local: bool = False


class AccessDeniedError(Exception):
    """请求身份无权访问目标资源。"""


# --------------------------------------------------------------------------- #
# 管理员专属路径
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# 辅助函数
# --------------------------------------------------------------------------- #

def _public_settings(settings: dict) -> dict:
    """返回可通过 HTTP 暴露的设置，绝不包含密钥原文。"""
    public = dict(settings)
    for field in _SECRET_SETTING_FIELDS:
        value = public.pop(field, None)
        configured = bool(value is not None and str(value).strip())
        public[f"{field}_configured"] = configured
        public[f"{field}_masked"] = "*" * len(str(value)) if configured else ""
    return public


def _settings_update_payload(data: dict) -> dict:
    """过滤设置更新中的空值/掩码密钥，保持已有密钥。"""
    payload = dict(data)
    for field in _SECRET_SETTING_FIELDS:
        if field in payload and db.is_secret_placeholder(payload[field]):
            payload.pop(field, None)
    payload.pop("smtp_password_configured", None)
    payload.pop("pushplus_token_configured", None)
    return payload


def _with_status(sub: dict) -> dict:
    sub = dict(sub)
    sub["status"] = domain.derive_status(sub.get("lifecycle", "active"), sub.get("next_due_date"))
    sub["status_label"] = domain.STATUS_LABELS.get(sub["status"], sub["status"])
    sub["status_color"] = domain.STATUS_COLORS.get(sub["status"], "#6B7280")
    return sub


def _resolve_backup_file(name: str) -> Path:
    """把备份文件名解析为备份目录内的安全路径，防止路径穿越。"""
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


def _read_log_tail(log_path: Path, lines: int) -> dict:
    """从文件尾部倒读最近 N 行日志。"""
    if not log_path.is_file():
        return {"file": log_path.name, "lines": [], "error": None}
    try:
        with open(log_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = 8192
            tail = b""
            pos = size
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


# --------------------------------------------------------------------------- #
# Flask 应用工厂
# --------------------------------------------------------------------------- #

def create_app(*, allow_headerless_local_identity: bool = False) -> Flask:
    """创建并配置 Flask 应用。

    Parameters
    ----------
    allow_headerless_local_identity : bool
        本地 TCP 开发模式允许无身份头请求（回退为 local 管理员）。
    """
    app = Flask(
        __name__,
        static_folder=str(config.www_dir()),
        static_url_path="",
    )
    app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BODY_BYTES
    app.config["JSON_AS_ASCII"] = False

    # 存储模式标志，供 before_request 使用
    app.config["ALLOW_HEADERLESS_LOCAL"] = allow_headerless_local_identity

    # ------------------------------------------------------------------ #
    # 请求钩子
    # ------------------------------------------------------------------ #

    @app.before_request
    def parse_identity() -> None:
        """解析网关身份，注入 g.identity。"""
        raw_user_id = request.headers.get("X-Trim-Userid")
        raw_is_admin = request.headers.get("X-Trim-Isadmin")
        raw_username = request.headers.get("X-Trim-Username")

        if raw_user_id is None and raw_is_admin is None:
            if not app.config["ALLOW_HEADERLESS_LOCAL"]:
                raise ValueError("Unix Socket 模式必须携带 X-Trim-Userid 身份头")
            g.identity = RequestIdentity(
                user_id="local",
                is_admin=True,
                username=raw_username or "local",
                is_local=True,
            )
            return

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

        is_admin = _parse_admin_flag(raw_is_admin)
        g.identity = RequestIdentity(
            user_id=user_id,
            is_admin=is_admin,
            username=username,
            is_local=False,
        )

    @app.before_request
    def check_admin_only() -> None:
        """管理员专属路径权限校验。"""
        protected = _ADMIN_ONLY_PATHS.get(request.path)
        if protected and not g.identity.is_admin:
            raise AccessDeniedError(f"仅管理员可访问{protected}")

    @app.before_request
    def ensure_default_categories() -> None:
        """新用户首次访问 API 时补种默认分类（幂等）。"""
        if request.path.startswith("/api/"):
            db.ensure_default_categories_for_user(g.identity.user_id)

    # ------------------------------------------------------------------ #
    # 错误处理
    # ------------------------------------------------------------------ #

    @app.errorhandler(AccessDeniedError)
    def handle_access_denied(exc: AccessDeniedError) -> Response:
        return jsonify({"error": str(exc)}), 403

    @app.errorhandler(ValueError)
    def handle_value_error(exc: ValueError) -> Response:
        msg = str(exc)
        if "已存在" in msg or "已达上限" in msg:
            return jsonify({"error": msg}), 409
        return jsonify({"error": msg}), 400

    @app.errorhandler(404)
    def handle_not_found(exc) -> Response:
        return jsonify({"error": "接口不存在"}), 404

    @app.errorhandler(413)
    def handle_payload_too_large(exc) -> Response:
        return jsonify({"error": f"请求体过大，不能超过 {MAX_REQUEST_BODY_BYTES} 字节"}), 413

    @app.errorhandler(500)
    def handle_internal_error(exc) -> Response:
        log.exception("API 处理失败")
        return jsonify({"error": "服务器内部错误"}), 500

    # ------------------------------------------------------------------ #
    # 网关路径归一化
    # ------------------------------------------------------------------ #

    @app.before_request
    def normalize_gateway_path() -> None:
        """统一网关会把 gatewayPrefix 原样转发给应用。

        剥离前缀，使 /app/subscription/... 与本地直接访问 / 等价。
        """
        path = request.path
        prefix = config.gateway_prefix()

        if path == prefix or path == prefix + "/":
            # 重定向到根路径
            return redirect("/")

        if path.startswith(prefix + "/"):
            # Flask 的 request.path 是只读的，用 url_rule 无法动态修改。
            # 通过 WSGI environ 修改 SCRIPT_NAME / PATH_INFO 实现前缀剥离。
            request.environ["PATH_INFO"] = path[len(prefix):] or "/"
            request.environ["SCRIPT_NAME"] = prefix
            return

        if path == "/app":
            return redirect("/")

        if path.startswith("/app/"):
            candidate = "/" + path[len("/app/"):]
            if _is_internal_path(candidate):
                request.environ["PATH_INFO"] = candidate
                request.environ["SCRIPT_NAME"] = "/app"
                return

    # ------------------------------------------------------------------ #
    # 订阅 API
    # ------------------------------------------------------------------ #

    @app.route("/api/subscriptions", methods=["GET"])
    def list_subscriptions() -> Response:
        subs = db.get_all_subscriptions(g.identity.user_id)
        return jsonify([_with_status(s) for s in subs])

    @app.route("/api/subscriptions", methods=["POST"])
    def create_subscription() -> Response:
        sub = db.create_subscription(g.identity.user_id, request.get_json(force=True))
        return jsonify(_with_status(sub)), 201

    @app.route("/api/subscriptions/<sub_id>", methods=["GET"])
    def get_subscription(sub_id: str) -> Response:
        sub = db.get_subscription_by_id(sub_id, g.identity.user_id)
        if sub is None:
            return jsonify({"error": "订阅不存在"}), 404
        return jsonify(_with_status(sub))

    @app.route("/api/subscriptions/<sub_id>", methods=["PUT"])
    def update_subscription(sub_id: str) -> Response:
        sub = db.update_subscription(sub_id, g.identity.user_id, request.get_json(force=True))
        if sub is None:
            return jsonify({"error": "订阅不存在"}), 404
        return jsonify(_with_status(sub))

    @app.route("/api/subscriptions/<sub_id>", methods=["DELETE"])
    def delete_subscription(sub_id: str) -> Response:
        ok = db.delete_subscription(sub_id, g.identity.user_id)
        if not ok:
            return jsonify({"error": "订阅不存在"}), 404
        return jsonify({"ok": True})

    @app.route("/api/subscriptions/<sub_id>/renew", methods=["POST"])
    def renew_subscription(sub_id: str) -> Response:
        sub = db.renew_subscription(sub_id, g.identity.user_id)
        if sub is None:
            return jsonify({"error": "订阅不存在"}), 404
        return jsonify(_with_status(sub))

    # ------------------------------------------------------------------ #
    # 分类 API
    # ------------------------------------------------------------------ #

    @app.route("/api/categories", methods=["GET"])
    def list_categories() -> Response:
        return jsonify(db.get_all_categories(g.identity.user_id))

    @app.route("/api/categories", methods=["POST"])
    def create_category() -> Response:
        try:
            cat = db.create_category(g.identity.user_id, request.get_json(force=True))
        except ValueError as exc:
            msg = str(exc)
            if "已存在" in msg or "已达上限" in msg:
                return jsonify({"error": msg}), 409
            raise
        return jsonify(cat), 201

    @app.route("/api/categories/<cat_id>", methods=["PUT"])
    def update_category(cat_id: str) -> Response:
        try:
            cat = db.update_category(cat_id, g.identity.user_id, request.get_json(force=True))
        except ValueError as exc:
            msg = str(exc)
            if "已存在" in msg or "已达上限" in msg:
                return jsonify({"error": msg}), 409
            raise
        if cat is None:
            return jsonify({"error": "分类不存在"}), 404
        return jsonify(cat)

    @app.route("/api/categories/<cat_id>", methods=["DELETE"])
    def delete_category(cat_id: str) -> Response:
        ok = db.delete_category(cat_id, g.identity.user_id)
        if not ok:
            return jsonify({"error": "分类不存在"}), 404
        return jsonify({"ok": True})

    # ------------------------------------------------------------------ #
    # 设置 API
    # ------------------------------------------------------------------ #

    @app.route("/api/settings", methods=["GET"])
    def get_settings() -> Response:
        return jsonify(_public_settings(db.get_app_settings()))

    @app.route("/api/settings", methods=["PUT"])
    def update_settings() -> Response:
        payload = _settings_update_payload(request.get_json(force=True))
        return jsonify(_public_settings(db.update_app_settings(payload)))

    # ------------------------------------------------------------------ #
    # 统计 & 日历 API
    # ------------------------------------------------------------------ #

    @app.route("/api/statistics", methods=["GET"])
    def get_statistics() -> Response:
        mode = request.args.get("mode", "nominal")
        return jsonify(statistics.calculate_statistics(g.identity.user_id, mode))

    @app.route("/api/calendar", methods=["GET"])
    def get_calendar() -> Response:
        year = int(request.args.get("year", date.today().year))
        month = int(request.args.get("month", date.today().month))
        return jsonify(statistics.get_calendar_events(g.identity.user_id, year, month))

    # ------------------------------------------------------------------ #
    # 备份 API
    # ------------------------------------------------------------------ #

    @app.route("/api/backup", methods=["POST"])
    def trigger_backup() -> Response:
        return jsonify(scheduler.backup_now(include_all=True))

    @app.route("/api/backup/export-json", methods=["GET"])
    def export_json() -> Response:
        return Response(
            backup.export_json_string(include_all=True),
            mimetype="application/json; charset=utf-8",
        )

    @app.route("/api/backup/import-json", methods=["POST"])
    def import_json() -> Response:
        result = backup.import_from_json(request.get_data(as_text=True), g.identity.user_id)
        return jsonify(result)

    @app.route("/api/backup/import-csv", methods=["POST"])
    def import_csv() -> Response:
        result = backup.import_from_csv(request.get_data(as_text=True), g.identity.user_id)
        return jsonify(result)

    @app.route("/api/backup/files", methods=["GET"])
    def list_backup_files() -> Response:
        return jsonify(_list_backup_files())

    @app.route("/api/backup/files", methods=["DELETE"])
    def delete_backup_file() -> Response:
        name = request.args.get("name", "")
        ok = _delete_backup_file(name)
        return jsonify({"ok": ok}), 200 if ok else 404

    @app.route("/api/backup/files/download", methods=["GET"])
    def download_backup_file() -> Response:
        name = request.args.get("name", "")
        try:
            file_path = _resolve_backup_file(name)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if not file_path.is_file():
            return jsonify({"error": "备份文件不存在"}), 404
        return send_file(
            file_path,
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=file_path.name,
        )

    @app.route("/api/export/csv", methods=["GET"])
    def export_csv() -> Response:
        return Response(
            backup.export_csv(include_all=True),
            mimetype="text/csv; charset=utf-8",
        )

    # ------------------------------------------------------------------ #
    # 通知 API
    # ------------------------------------------------------------------ #

    @app.route("/api/notifications/upcoming", methods=["GET"])
    def upcoming_notifications() -> Response:
        return jsonify(_upcoming_notifications(g.identity.user_id))

    @app.route("/api/notifications/test-email", methods=["POST"])
    def test_email() -> Response:
        payload = request.get_json(force=True)
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
            return jsonify({"ok": False, "error": f"邮件发送失败: {exc}"}), 400

        return jsonify({"ok": True, "message": f"测试邮件已发送至 {to_address}"})

    @app.route("/api/notifications/test-pushplus", methods=["POST"])
    def test_pushplus() -> Response:
        payload = request.get_json(force=True)
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
            return jsonify({"ok": False, "error": f"PushPlus 发送失败: {exc}"}), 400

        return jsonify({"ok": True, "message": "测试推送已发送成功"})

    # ------------------------------------------------------------------ #
    # 日志 API
    # ------------------------------------------------------------------ #

    @app.route("/api/logs/tail", methods=["GET"])
    def log_tail() -> Response:
        try:
            want = min(int(request.args.get("lines", "200")), 1000)
        except ValueError:
            want = 200
        return jsonify(_read_log_tail(config.logs_dir() / "app.log", want))

    # ------------------------------------------------------------------ #
    # 静态文件（Flask 内置 static 处理 + SPA fallback）
    # ------------------------------------------------------------------ #

    @app.route("/")
    def serve_index() -> Response:
        index = config.www_dir() / "index.html"
        if index.is_file():
            return send_file(index)
        return jsonify({"error": "Not Found"}), 404

    @app.route("/<path:path>")
    def serve_static(path: str) -> Response:
        root = config.www_dir().resolve()
        target = (root / path).resolve()
        if not _is_path_within(root, target) or not target.is_file():
            # SPA fallback: 非 API 路径返回 index.html
            index = root / "index.html"
            if index.is_file():
                return send_file(index)
            return jsonify({"error": "Not Found"}), 404
        return send_file(target)

    return app


# --------------------------------------------------------------------------- #
# 辅助
# --------------------------------------------------------------------------- #

def _parse_admin_flag(raw_value: str | None) -> bool:
    if raw_value is None:
        return False
    value = raw_value.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"", "0", "false", "no", "off"}:
        return False
    raise ValueError("X-Trim-Isadmin 必须为 true/false")


def _is_internal_path(path: str) -> bool:
    """判断剥离候选前缀后的路径是否确实是本应用内部路径。"""
    if path == "/" or path.startswith("/api/"):
        return True
    root = config.www_dir().resolve()
    rel = path.lstrip("/")
    if not rel:
        return True
    target = (root / rel).resolve()
    return _is_path_within(root, target) and target.is_file()


def _is_path_within(root: Path, target: Path) -> bool:
    try:
        target.relative_to(root)
    except ValueError:
        return False
    return True


# --------------------------------------------------------------------------- #
# 日志
# --------------------------------------------------------------------------- #

_LOG_RETENTION_DAYS = 30
_LOG_MAX_BYTES = 2 * 1024 * 1024
_LOG_BACKUP_COUNT = 5


def _setup_logging(log_dir: Path, console: bool) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler = logging.handlers.RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=_LOG_MAX_BYTES,
        backupCount=_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(formatter)
    root = logging.getLogger(scheduler.LOGGER_NAME)
    root.setLevel(logging.DEBUG if os.environ.get("SUBSCRIPTION_DEBUG") == "1" else logging.INFO)
    root.addHandler(handler)
    if console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)
    _cleanup_old_logs(log_dir)


def _cleanup_old_logs(log_dir: Path) -> None:
    """启动时清理超过保留期的轮转/历史日志文件。"""
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


# --------------------------------------------------------------------------- #
# Unix Socket 服务器
# --------------------------------------------------------------------------- #

def _run_unix_socket(app: Flask, sock_path: str) -> None:
    """在 Unix domain socket 上运行 Flask 应用。"""
    import threading
    from http.server import HTTPServer

    from werkzeug.serving import WSGIRequestHandler

    class UnixWSGIServer(HTTPServer):
        """基于 HTTPServer 的 Unix Socket WSGI 服务器。"""
        address_family = __import__("socket").AF_UNIX
        allow_headerless_local_identity = False

        def server_bind(self) -> None:
            if os.path.exists(self.server_address):
                try:
                    os.unlink(self.server_address)
                except OSError:
                    pass
            super().server_bind()

    class ThreadedUnixWSGIServer(UnixWSGIServer):
        """多线程版本。"""
        def process_request(self, request, client_address) -> None:
            t = threading.Thread(target=self.process_request_thread, args=(request, client_address))
            t.daemon = True
            t.start()

        def process_request_thread(self, request, client_address) -> None:
            try:
                self.finish_request(request, client_address)
            except Exception:
                self.handle_error(request, client_address)
            finally:
                self.shutdown_request(request)

    class QuietHandler(WSGIRequestHandler):
        """抑制 werkzeug 默认的请求日志（我们有自己的 logger）。"""
        def log_request(self, code="-", size="-") -> None:
            pass

    from werkzeug.serving import run_simple

    # werkzeug 的 run_simple 不直接支持 Unix Socket，手动创建服务器
    server = ThreadedUnixWSGIServer(sock_path, QuietHandler)
    server.app = app  # type: ignore[attr-defined]

    from werkzeug.server import WSGIRequestHandler as _WRH

    class UnixHandler(_WRH):
        """让 werkzeug WSGI handler 在 Unix Socket 上工作。"""
        def run(self, application) -> None:
            self.server.app = application  # type: ignore[attr-defined]
            from werkzeug.serving import WSGIRequestHandler as _W
            _W.run(self, application)

    log.info("监听统一网关 Unix Socket: %s", sock_path)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("退出")
    finally:
        server.server_close()
        if os.path.exists(sock_path):
            os.unlink(sock_path)


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #

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

    allow_headerless = not is_gateway
    app = create_app(allow_headerless_local_identity=allow_headerless)

    if is_gateway:
        sock_path = args.uds or str(Path(os.environ["TRIM_APPDEST"]) / "app.sock")
        _run_unix_socket(app, sock_path)
    else:
        port = args.http or 8000
        log.info("监听 http://127.0.0.1:%d", port)
        app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
