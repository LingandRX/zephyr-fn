"""备份 / 导入导出 API（管理员专属，由全局中间件校验）。

下载类端点（export-json / export-csv / 备份文件下载）保持原始文件响应，
不走统一 JSON 信封；浏览器以导航方式直接触发下载。
"""
from __future__ import annotations

from flask import Blueprint, Response, g, request, send_file

from ..core.exceptions import NotFoundError, ValidationError
from ..core.response import ok
from ..services import backup as backup_service
from ..services import scheduler

bp = Blueprint("api_backup", __name__, url_prefix="/api")


@bp.route("/backup", methods=["POST"])
def trigger_backup():
    return ok(scheduler.backup_now(include_all=True))


@bp.route("/backup/export-json", methods=["GET"])
def export_json():
    return Response(
        backup_service.export_json_string(include_all=True),
        mimetype="application/json; charset=utf-8",
    )


@bp.route("/backup/import-json", methods=["POST"])
def import_json():
    result = backup_service.import_from_json(
        request.get_data(as_text=True), g.identity.user_id
    )
    return ok(result)


@bp.route("/backup/import-csv", methods=["POST"])
def import_csv():
    result = backup_service.import_from_csv(
        request.get_data(as_text=True), g.identity.user_id
    )
    return ok(result)


@bp.route("/backup/files", methods=["GET"])
def list_backup_files():
    return ok(backup_service.list_backup_files())


@bp.route("/backup/files", methods=["DELETE"])
def delete_backup_file():
    name = request.args.get("name", "")
    if not backup_service.delete_backup_file(name):
        raise NotFoundError("备份文件不存在")
    return ok({"ok": True})


@bp.route("/backup/files/download", methods=["GET"])
def download_backup_file():
    name = request.args.get("name", "")
    try:
        file_path = backup_service.resolve_backup_file(name)
    except ValueError as exc:
        raise ValidationError(str(exc))
    if not file_path.is_file():
        raise NotFoundError("备份文件不存在")
    return send_file(
        file_path,
        mimetype="application/octet-stream",
        as_attachment=True,
        download_name=file_path.name,
    )


@bp.route("/export/csv", methods=["GET"])
def export_csv():
    return Response(
        backup_service.export_csv(include_all=True),
        mimetype="text/csv; charset=utf-8",
    )
