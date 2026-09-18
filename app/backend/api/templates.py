"""订阅模板 API 蓝图。"""

from __future__ import annotations

from flask import Blueprint, request

from ..services import templates as templates_service
from ..web.response import ok

bp = Blueprint("api_templates", __name__, url_prefix="/api")


@bp.route("/templates", methods=["GET"])
def get_templates():
    """获取当前生效的订阅模板及分类。"""
    return ok(templates_service.get_active_templates())


@bp.route("/templates/sync", methods=["POST"])
def sync_templates():
    """同步远程订阅模板。"""
    body = request.get_json(silent=True) or {}
    url = body.get("url") if isinstance(body, dict) else None
    return ok(templates_service.sync_remote_templates(url=url))


@bp.route("/templates/reset", methods=["POST"])
def reset_templates():
    """重置为出厂内置默认模板。"""
    return ok(templates_service.reset_templates())
