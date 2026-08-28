"""日志 API。"""
from __future__ import annotations

import os

from flask import Blueprint, request

from .. import config
from ..core.response import ok

bp = Blueprint("api_logs", __name__, url_prefix="/api")


@bp.route("/logs/tail", methods=["GET"])
def log_tail():
    try:
        want = min(int(request.args.get("lines", "200")), 1000)
    except ValueError:
        want = 200
    return ok(_read_log_tail(config.logs_dir() / "app.log", want))


def _read_log_tail(log_path, lines: int) -> dict:
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
