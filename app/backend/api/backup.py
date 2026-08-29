"""CSV 导入导出 API（管理员专属，由全局中间件校验）。

导出端点（export-csv）保持原始文件响应，不走统一 JSON 信封；
浏览器以导航方式直接触发下载。
"""
from __future__ import annotations

from flask import Blueprint, Response, g, request

from ..core.response import ok
from ..services import backup as backup_service

bp = Blueprint("api_backup", __name__, url_prefix="/api")


def _csv_response(content: str, filename: str) -> Response:
    """构造标准 CSV 下载响应。

    要点：
    - mimetype 只传 ``text/csv``，由 Werkzeug 自动补 ``; charset=utf-8``；
      若在 mimetype 里再写 charset 会得到 ``text/csv; charset=utf-8; charset=utf-8``
      这种畸形头，部分浏览器（含 Chrome）在识别下载类型时失败，报“无法在网站提取文件”。
    - ``Content-Disposition`` 同时提供 ASCII filename 与 UTF-8 filename*，保证中文文件名兼容。
    - 显式设置 ``Content-Length`` 与 ``X-Content-Type-Options: nosniff``，
      避免网关/代理二次编码后长度不符导致的 ERR_INVALID_RESPONSE。
    """
    body = content.encode("utf-8")
    response = Response(body, mimetype="text/csv")
    response.headers["Content-Disposition"] = (
        f"attachment; filename={filename}; filename*=UTF-8''{filename}"
    )
    response.headers["Content-Length"] = str(len(body))
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@bp.route("/backup/import-csv", methods=["POST"])
def import_csv():
    result = backup_service.import_from_csv(
        request.get_data(as_text=True), g.identity.user_id
    )
    return ok(result)


@bp.route("/export/csv", methods=["GET"])
def export_csv():
    return _csv_response(backup_service.export_csv(include_all=True), "subscriptions.csv")


@bp.route("/backup/import-template", methods=["GET"])
def import_template():
    return _csv_response(backup_service.csv_template(), "import_template.csv")