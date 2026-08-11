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
        GET           /api/export/csv
  通知  GET           /api/notifications/upcoming
"""
from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
import socket
import socketserver
import sys
import urllib.parse
from datetime import date
from http import HTTPStatus
from pathlib import Path

import backup
import config
import db
import domain
import notifications
import scheduler
import services

log = logging.getLogger(scheduler.LOGGER_NAME)


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
        request_line = self.rfile.readline()
        if not request_line:
            return
        try:
            method, raw_target, _proto = request_line.decode("latin-1").strip().split(" ", 2)
        except ValueError:
            return

        headers: dict[str, str] = {}
        while True:
            line = self.rfile.readline()
            if line in (b"\r\n", b"\n", b""):
                break
            if b":" in line:
                name, _, value = line.decode("latin-1").partition(":")
                headers[name.strip().lower()] = value.strip()

        try:
            content_length = int(headers.get("content-length") or 0)
        except ValueError:
            content_length = 0
        body = self.rfile.read(content_length) if content_length > 0 else b""

        self._route(method, raw_target, headers, body)

    # ----- 路由 -----

    def _route(self, method: str, raw_target: str, headers: dict, body: bytes) -> None:
        parsed = urllib.parse.urlsplit(raw_target)
        path = self._normalize_path(parsed.path)
        query = urllib.parse.parse_qs(parsed.query)
        user_id = headers.get("x-trim-userid") or "local"

        # 挂载路径不带结尾斜杠时 302 跳转，避免相对资源（style.css/app.js）
        # 解析到上一层目录（/app/...）导致网关 404。
        if not parsed.path.endswith("/") and path == "/":
            self._redirect(parsed.path + "/")
            return

        try:
            if path == "/api/subscriptions" and method == "GET":
                self._json([_with_status(s) for s in db.get_all_subscriptions(user_id)])
            elif path == "/api/subscriptions" and method == "POST":
                self._json(_with_status(db.create_subscription(user_id, self._json_body(body))),
                           HTTPStatus.CREATED)
            elif path == "/api/categories" and method == "GET":
                self._json(db.get_all_categories(user_id))
            elif path == "/api/categories" and method == "POST":
                self._json(db.create_category(user_id, self._json_body(body)),
                           HTTPStatus.CREATED)
            elif path == "/api/settings" and method == "GET":
                self._json(db.get_app_settings())
            elif path == "/api/settings" and method == "PUT":
                self._json(db.update_app_settings(self._json_body(body)))
            elif path == "/api/statistics" and method == "GET":
                mode = (query.get("mode") or ["nominal"])[0]
                self._json(services.calculate_statistics(user_id, mode))
            elif path == "/api/calendar" and method == "GET":
                year = int((query.get("year") or [date.today().year])[0])
                month = int((query.get("month") or [date.today().month])[0])
                self._json(services.get_calendar_events(user_id, year, month))
            elif path == "/api/backup" and method == "POST":
                self._json(scheduler.backup_now())
            elif path == "/api/backup/export-json" and method == "GET":
                self._raw_text(backup.export_json_string(), "application/json; charset=utf-8")
            elif path == "/api/backup/import-json" and method == "POST":
                result = backup.import_from_json(body.decode("utf-8"), user_id)
                self._json(result)
            elif path == "/api/backup/import-csv" and method == "POST":
                result = backup.import_from_csv(body.decode("utf-8"), user_id)
                self._json(result)
            elif path == "/api/backup/files" and method == "GET":
                self._json(_list_backup_files())
            elif path == "/api/export/csv" and method == "GET":
                self._raw_text(backup.export_csv(), "text/csv; charset=utf-8")
            elif path == "/api/notifications/upcoming" and method == "GET":
                self._json(_upcoming_notifications(user_id))
            elif path.startswith("/api/subscriptions/"):
                self._route_subscription(method, path, user_id, body)
            elif path.startswith("/api/categories/"):
                self._route_category(method, path, user_id, body)
            else:
                self._serve_static(path)
        except ValueError as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception:  # noqa: BLE001
            log.exception("API 处理失败: %s %s", method, path)
            self._json({"error": "服务器内部错误"}, HTTPStatus.INTERNAL_SERVER_ERROR)

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
            cat = db.update_category(cat_id, user_id, self._json_body(body))
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
        return str(target).startswith(str(root)) and target.is_file()

    # ----- 静态文件 -----

    def _serve_static(self, path: str) -> None:
        root = config.www_dir().resolve()
        rel = path.lstrip("/") or "index.html"
        if not rel:
            rel = "index.html"
        target = (root / rel).resolve()
        if not str(target).startswith(str(root)) or not target.is_file():
            self._error(HTTPStatus.NOT_FOUND, "Not Found")
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        data = target.read_bytes()
        cache = rel != "index.html"
        self._raw(HTTPStatus.OK, ctype, data, cache=cache)

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

    def _raw(self, status, ctype: str, body: bytes, cache: bool = False) -> None:
        code = int(status)
        phrase = HTTPStatus(code).phrase
        head = (
            f"HTTP/1.1 {code} {phrase}\r\n"
            f"Content-Type: {ctype}\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"{'Cache-Control: public, max-age=3600' if cache else 'Cache-Control: no-store'}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
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
    reminder_days = max(0, int(settings.get("notification_days") or 3))
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

class ThreadingUnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

    def server_bind(self) -> None:
        if os.path.exists(self.server_address):
            try:
                os.unlink(self.server_address)
            except OSError:
                pass
        super().server_bind()


class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def _setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_dir / "app.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger(scheduler.LOGGER_NAME)
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    root.addHandler(logging.StreamHandler(sys.stderr))


def main() -> None:
    parser = argparse.ArgumentParser(description="订阅管理 HTTP 服务")
    parser.add_argument("--uds", help="Unix domain socket 路径（网关模式）")
    parser.add_argument("--http", type=int, help="TCP 端口（本地调试）")
    parser.add_argument("--db", help="数据库文件路径")
    parser.add_argument("--www", help="前端静态目录")
    parser.add_argument("--share", help="备份目录")
    parser.add_argument("--init-db", action="store_true", help="仅初始化数据库后退出")
    args = parser.parse_args()

    config.override("DB_PATH", args.db)
    config.override("WWW_DIR", args.www)
    config.override("SHARE_DIR", args.share)

    db.connect(config.db_path())
    if args.init_db:
        print(f"数据库就绪: {config.db_path()}")
        return

    _setup_logging(config.logs_dir())
    log.info("启动订阅管理 v%s (arch=%s)", config.app_version(), config.sys_arch())

    scheduler.start_scheduler(config.reminder_days())
    log.info("定时任务已启动 (提醒提前 %s 天, 备份目录 %s)",
             config.reminder_days(), config.backup_dir())

    sock_path = args.uds
    if sock_path or os.environ.get("TRIM_APPDEST"):
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
        if isinstance(server, ThreadingUnixServer) and os.path.exists(sock_path):
            os.unlink(sock_path)


if __name__ == "__main__":
    main()
