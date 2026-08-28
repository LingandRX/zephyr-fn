"""静态资源与 SPA fallback（非 API 路径）。"""
from __future__ import annotations

from flask import Blueprint, Response, jsonify, send_file

from .. import config
from ..core.middleware import is_path_within

bp = Blueprint("api_web", __name__)


@bp.route("/")
def serve_index() -> Response:
    index = config.www_dir() / "index.html"
    if index.is_file():
        return send_file(index)
    return jsonify({"code": 404, "message": "Not Found", "data": None}), 404


@bp.route("/<path:path>")
def serve_static(path: str) -> Response:
    root = config.www_dir().resolve()
    target = (root / path).resolve()
    if not is_path_within(root, target) or not target.is_file():
        # SPA fallback: 非 API 路径返回 index.html
        index = root / "index.html"
        if index.is_file():
            return send_file(index)
        return jsonify({"code": 404, "message": "Not Found", "data": None}), 404
    return send_file(target)
