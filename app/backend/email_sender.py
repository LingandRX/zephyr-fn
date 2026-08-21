"""邮件通知（Python 标准库 smtplib）。"""
from __future__ import annotations

import smtplib
from email.mime.text import MIMEText
from email.header import Header

try:  # 包模式与直接从 backend 目录启动模式兼容。
    from . import db
except ImportError:  # pragma: no cover
    import db


def send_email(
    to_address: str,
    subject: str,
    body: str,
    *,
    host: str | None = None,
    port: int | str | None = None,
    username: str | None = None,
    password: str | None = None,
    from_address: str | None = None,
) -> None:
    settings = db.get_app_settings() if (
        host is None or port is None or username is None or password is None or from_address is None
    ) else {}

    smtp_host = host if host is not None else settings.get("smtp_host")
    if not smtp_host:
        raise RuntimeError("未配置 SMTP 服务器")

    raw_port = port if port is not None else settings.get("smtp_port")
    try:
        smtp_port = int(raw_port or 465)
    except (ValueError, TypeError):
        smtp_port = 465

    smtp_user = username if username is not None else settings.get("smtp_username")
    smtp_pass = password if password is not None else settings.get("smtp_password")
    smtp_from = from_address if from_address is not None else (settings.get("smtp_from_address") or smtp_user)

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = smtp_from or "subscription@localhost"
    msg["To"] = to_address

    if smtp_port == 465:
        server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
    else:
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
        server.starttls()
    try:
        if smtp_user:
            server.login(smtp_user, smtp_pass or "")
        server.sendmail(smtp_from or "subscription@localhost", [to_address], msg.as_string())
    finally:
        try:
            server.quit()
        except Exception:
            pass

