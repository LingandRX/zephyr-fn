"""订阅 API。"""
from __future__ import annotations

from flask import Blueprint, g, request

from ..core.exceptions import NotFoundError
from ..core.response import ok
from ..services import subscriptions

bp = Blueprint("api_subscriptions", __name__, url_prefix="/api")


@bp.route("/subscriptions", methods=["GET"])
def list_subscriptions():
    subs = subscriptions.list_subscriptions(g.identity.user_id)
    return ok([subscriptions.with_status(s) for s in subs])


@bp.route("/subscriptions", methods=["POST"])
def create_subscription():
    sub = subscriptions.create_subscription(
        g.identity.user_id, request.get_json(force=True)
    )
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


@bp.route("/subscriptions/<sub_id>/renew", methods=["POST"])
def renew_subscription(sub_id: str):
    sub = subscriptions.renew_subscription(sub_id, g.identity.user_id)
    if sub is None:
        raise NotFoundError("订阅不存在或为一次性订阅")
    return ok(subscriptions.with_status(sub))
