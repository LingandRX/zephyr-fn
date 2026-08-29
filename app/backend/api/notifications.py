"""通知 API（即将到期 / 渠道测试）。"""
from __future__ import annotations

from datetime import date

from flask import Blueprint, g, request

from ..core.exceptions import ValidationError
from ..core.response import ok
from ..services import notifications
from ..services import settings as settings_service
from ..utils.channels import email as email_sender
from ..utils.channels import pushplus

bp = Blueprint("api_notifications", __name__, url_prefix="/api")


@bp.route("/notifications/upcoming", methods=["GET"])
def upcoming_notifications():
    return ok(notifications.get_upcoming_notifications(g.identity.user_id))


@bp.route("/notifications/test-email", methods=["POST"])
def test_email():
    payload = request.get_json(force=True)
    settings = settings_service.get_raw_settings()

    host = payload.get("smtp_host") or settings.get("smtp_host")
    if not host:
        raise ValidationError("请先填写或配置 SMTP 服务器")

    port_raw = payload.get("smtp_port") or settings.get("smtp_port") or 465
    try:
        port = int(port_raw)
    except (ValueError, TypeError):
        port = 465
    username = payload.get("smtp_username") or settings.get("smtp_username")
    from_address = (
        payload.get("smtp_from_address")
        or settings.get("smtp_from_address")
        or username
    )

    password_draft = payload.get("smtp_password")
    if password_draft and not _is_secret_placeholder(password_draft):
        password = password_draft
    else:
        password = settings.get("smtp_password")

    to_address = (
        payload.get("to_address")
        or payload.get("smtp_to_address")
        or from_address
        or username
    )
    if not to_address:
        raise ValidationError("请提供测试接收邮箱（或配置发件人/用户名）")

    subject = "【订阅管理】邮件通知测试"
    content = (
        "这是一封来自订阅管理系统的测试邮件。\n\n"
        f"发送时间：{date.today().isoformat()}\n"
        "如果您看到这封邮件，说明您的 SMTP 邮件通知配置正确并已成功生效。"
    )

    try:
        email_sender.send_email(
            to_address=to_address,
            subject=subject,
            body=content,
            host=host,
            port=port,
            username=username,
            password=password,
            from_address=from_address,
        )
    except Exception as exc:
        return ok({"ok": False, "error": f"邮件发送失败: {exc}"})

    return ok({"ok": True, "message": f"测试邮件已发送至 {to_address}"})


@bp.route("/notifications/test-pushplus", methods=["POST"])
def test_pushplus():
    payload = request.get_json(force=True)
    settings = settings_service.get_raw_settings()

    token_draft = payload.get("pushplus_token")
    if token_draft and not _is_secret_placeholder(token_draft):
        token = token_draft
    else:
        token = settings.get("pushplus_token")

    if not token:
        raise ValidationError("请先填写或配置 PushPlus Token")

    title = "【订阅管理】PushPlus 推送测试"
    content = (
        "<p>这是一条来自订阅管理系统的测试消息。</p>"
        f"<p>发送时间：{date.today().isoformat()}</p>"
        "<p>如果您看到此消息，说明您的 PushPlus 微信推送配置正确并已成功生效。</p>"
    )

    # PushPlus 专用 SMTP 配置（优先），回退到通用 SMTP
    smtp_host = (
        payload.get("pushplus_smtp_host")
        or settings.get("pushplus_smtp_host")
        or payload.get("smtp_host")
        or settings.get("smtp_host")
    )
    smtp_port_raw = (
        payload.get("pushplus_smtp_port")
        or settings.get("pushplus_smtp_port")
        or payload.get("smtp_port")
        or settings.get("smtp_port")
        or 465
    )
    try:
        smtp_port = int(smtp_port_raw)
    except (ValueError, TypeError):
        smtp_port = 465
    smtp_username = (
        payload.get("pushplus_smtp_username")
        or settings.get("pushplus_smtp_username")
        or payload.get("smtp_username")
        or settings.get("smtp_username")
    )
    smtp_from_address = (
        payload.get("pushplus_smtp_from_address")
        or settings.get("pushplus_smtp_from_address")
        or payload.get("smtp_from_address")
        or settings.get("smtp_from_address")
        or smtp_username
    )
    password_draft = payload.get("pushplus_smtp_password") or payload.get("smtp_password")
    if password_draft and not _is_secret_placeholder(password_draft):
        smtp_password = password_draft
    else:
        smtp_password = settings.get("pushplus_smtp_password") or settings.get("smtp_password")

    try:
        pushplus.send_pushplus(
            token=token,
            title=title,
            content=content,
            host=smtp_host,
            port=smtp_port,
            username=smtp_username,
            password=smtp_password,
            from_address=smtp_from_address,
        )
    except Exception as exc:
        return ok({"ok": False, "error": f"PushPlus 发送失败: {exc}"})

    return ok({"ok": True, "message": "测试推送已发送成功"})


def _is_secret_placeholder(value) -> bool:
    from ..storage.repositories import is_secret_placeholder
    return is_secret_placeholder(value)
