#!/usr/bin/env python3
"""订阅管理 - HTTP API 服务入口（应用工厂 + UDS/TCP 启动）。

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
  备份  POST          /api/backup/import-csv
        GET           /api/export/csv
  通知  GET           /api/notifications/upcoming
  日志  GET           /api/logs/tail?lines=200

统一响应结构：{code, message, data}（code == 0 表示成功）。
"""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import sys
import time
from pathlib import Path

# 兼容直接执行（python3 server.py，cmd/main / dev.sh / install_callback 均如此）：
# 把 backend 包的父目录（app/）加入 sys.path，以包方式导入，
# 保证各模块的相对导入（from ..core import ...）统一生效。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import config  # noqa: E402
from backend.app import create_app  # noqa: E402
from backend.services import scheduler  # noqa: E402

log = logging.getLogger(scheduler.LOGGER_NAME)


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

def _run_unix_socket(app, sock_path: str) -> None:
    """在 Unix domain socket 上运行 Flask 应用。"""
    import threading
    from http.server import HTTPServer

    from werkzeug.serving import WSGIRequestHandler

    class UnixWSGIServer(HTTPServer):
        """基于 HTTPServer 的 Unix Socket WSGI 服务器。"""
        address_family = __import__("socket").AF_UNIX

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
    parser.add_argument("--init-db", action="store_true", help="仅初始化数据库后退出")
    parser.add_argument("--reminder-days", type=int,
                        help="安装向导提醒提前天数（配合 --init-db 使用）")
    args = parser.parse_args()

    config.override("DB_PATH", args.db)
    config.override("WWW_DIR", args.www)
    if args.reminder_days is not None:
        config.override("wizard_reminder_days", str(args.reminder_days))

    is_gateway = bool(args.uds or os.environ.get("TRIM_APPDEST"))

    # 工厂内部完成：旧库升级 + Alembic 迁移（幂等），--init-db 场景同时覆盖
    app = create_app(allow_headerless_local_identity=not is_gateway)
    if args.init_db:
        print(f"数据库就绪: {config.db_path()}")
        return

    _setup_logging(config.logs_dir(), console=not is_gateway)
    log.info("启动订阅管理 v%s (arch=%s)", config.app_version(), config.sys_arch())

    scheduler.start_scheduler(app)
    log.info("定时任务已启动")

    if is_gateway:
        sock_path = args.uds or str(Path(os.environ["TRIM_APPDEST"]) / "app.sock")
        _run_unix_socket(app, sock_path)
    else:
        port = args.http or 8000
        log.info("监听 http://127.0.0.1:%d", port)
        app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
