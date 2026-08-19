"""邮件通知（Python 标准库 smtplib）。"""
from __future__ import annotations

import smtplib
from email.mime.text import MIMEText
from email.header import Header

try:  # 包模式与直接从 backend 目录启动模式兼容。
    from . import db
except ImportError:  # pragma: no cover
    import db


def send_email(to_address: str, subject: str, body: str) -> None:
    settings = db.get_app_settings()
    host = settings.get("smtp_host")
    if not host:
        raise RuntimeError("未配置 SMTP 服务器")
    port = int(settings.get("smtp_port") or 465)
    username = settings.get("smtp_username")
    password = settings.get("smtp_password")
    from_address = settings.get("smtp_from_address") or username

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = from_address or "subscription@localhost"
    msg["To"] = to_address

    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=15)
    else:
        server = smtplib.SMTP(host, port, timeout=15)
        server.starttls()
    try:
        if username:
            server.login(username, password)
        server.sendmail(from_address, [to_address], msg.as_string())
    finally:
        server.quit()
