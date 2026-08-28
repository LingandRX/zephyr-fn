"""分类 API。"""
from __future__ import annotations

from flask import Blueprint, g, request

from ..core.exceptions import NotFoundError
from ..core.response import ok
from ..services import categories as category_service

bp = Blueprint("api_categories", __name__, url_prefix="/api")


@bp.route("/categories", methods=["GET"])
def list_categories():
    return ok(category_service.list_categories(g.identity.user_id))


@bp.route("/categories", methods=["POST"])
def create_category():
    category = category_service.create_category(
        g.identity.user_id, request.get_json(force=True)
    )
    return ok(category), 201


@bp.route("/categories/<cat_id>", methods=["PUT"])
def update_category(cat_id: str):
    category = category_service.update_category(
        cat_id, g.identity.user_id, request.get_json(force=True)
    )
    if category is None:
        raise NotFoundError("分类不存在")
    return ok(category)


@bp.route("/categories/<cat_id>", methods=["DELETE"])
def delete_category(cat_id: str):
    if not category_service.delete_category(cat_id, g.identity.user_id):
        raise NotFoundError("分类不存在")
    return ok({"ok": True})
