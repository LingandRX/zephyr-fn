"""订阅 API。"""

from __future__ import annotations

from flask import Blueprint, g, request

from ..domain.exceptions import NotFoundError, ValidationError
from ..http.response import ok
from ..services import subscriptions

bp = Blueprint("api_subscriptions", __name__, url_prefix="/api")


@bp.route("/subscriptions", methods=["GET"])
def list_subscriptions():
    # 支持分页：如果有 page 参数，返回分页结果；否则返回全量列表（向后兼容）
    if "page" in request.args:
        try:
            page = max(1, int(request.args.get("page", "1")))
        except (ValueError, TypeError):
            raise ValidationError("page 必须是正整数")

        per_page_raw = request.args.get("per_page", "20")
        try:
            per_page = max(1, min(100, int(per_page_raw)))
        except (ValueError, TypeError):
            raise ValidationError("per_page 必须是 1-100 的整数")

        lifecycle = request.args.get("lifecycle") or None
        category_id = request.args.get("category_id") or None

        result = subscriptions.list_subscriptions_paginated(
            user_id=g.identity.user_id,
            page=page,
            per_page=per_page,
            lifecycle=lifecycle,
            category_id=category_id,
        )
        return ok(result)

    # 向后兼容：无 page 参数时返回全量列表
    subs = subscriptions.list_subscriptions(g.identity.user_id)
    return ok([subscriptions.with_status(s) for s in subs])


@bp.route("/subscriptions", methods=["POST"])
def create_subscription():
    sub = subscriptions.create_subscription(g.identity.user_id, request.get_json(force=True))
    return ok(subscriptions.with_status(sub)), 201


@bp.route("/subscriptions/<sub_id>", methods=["GET"])
def get_subscription(sub_id: str):
    sub = subscriptions.get_subscription(sub_id, g.identity.user_id)
    if sub is None:
        raise NotFoundError("订阅不存在")
    return ok(subscriptions.with_status(sub))


@bp.route("/subscriptions/<sub_id>", methods=["PUT"])
def update_subscription(sub_id: str):
    sub = subscriptions.update_subscription(
        sub_id, g.identity.user_id, request.get_json(force=True)
    )
    if sub is None:
        raise NotFoundError("订阅不存在")
    return ok(subscriptions.with_status(sub))


@bp.route("/subscriptions/<sub_id>", methods=["DELETE"])
def delete_subscription(sub_id: str):
    if not subscriptions.delete_subscription(sub_id, g.identity.user_id):
        raise NotFoundError("订阅不存在")
    return ok({"ok": True})


@bp.route("/subscriptions/<sub_id>/restore", methods=["POST"])
def restore_subscription(sub_id: str):
    sub = subscriptions.restore_subscription(sub_id, g.identity.user_id)
    if sub is None:
        raise NotFoundError("已删除的订阅不存在")
    return ok(subscriptions.with_status(sub))


@bp.route("/subscriptions/<sub_id>/renew", methods=["POST"])
def renew_subscription(sub_id: str):
    sub = subscriptions.renew_subscription(sub_id, g.identity.user_id)
    if sub is None:
        raise NotFoundError("订阅不存在或为一次性订阅")
    return ok(subscriptions.with_status(sub))
