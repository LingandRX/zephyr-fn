"""统计与日历 API。"""
from __future__ import annotations

from datetime import date

from flask import Blueprint, g, request

from ..core.exceptions import ValidationError
from ..core.response import ok
from ..services.statistics import calculate_statistics, get_calendar_events

bp = Blueprint("api_statistics", __name__, url_prefix="/api")


@bp.route("/statistics", methods=["GET"])
def get_statistics():
    mode = request.args.get("mode", "nominal")
    if mode not in ("nominal", "actual"):
        raise ValidationError("统计模式必须是 nominal 或 actual")
    return ok(calculate_statistics(g.identity.user_id, mode))


@bp.route("/calendar", methods=["GET"])
def get_calendar():
    try:
        year = int(request.args.get("year", date.today().year))
        month = int(request.args.get("month", date.today().month))
    except ValueError as exc:
        raise ValidationError("year/month 必须是整数") from exc
    return ok(get_calendar_events(g.identity.user_id, year, month))
