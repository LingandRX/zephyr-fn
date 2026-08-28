"""应用设置 API（管理员专属，由全局中间件校验）。"""
from __future__ import annotations

from flask import Blueprint, request

from ..core.response import ok
from ..services import settings as settings_service

bp = Blueprint("api_settings", __name__, url_prefix="/api")


@bp.route("/settings", methods=["GET"])
def get_settings():
    return ok(settings_service.get_public_settings())


@bp.route("/settings", methods=["PUT"])
def update_settings():
    return ok(settings_service.update_settings(request.get_json(force=True)))
