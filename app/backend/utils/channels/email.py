"""邮件通知工具（Python 标准库 smtplib）。

纯基础设施：SMTP 参数一律由调用方传入（scheduler / 测试通知接口
从设置服务读取后传入），本模块不依赖任何存储层，保持分层纯净。
"""
from __future__ import annotations

import smtplib
from email.header import Header
from email.mime.text import MIMEText


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
    """通过 SMTP 发送单封文本邮件（host 必填）。"""
    smtp_host = host
    if not smtp_host:
        raise RuntimeError("未配置 SMTP 服务器")

    try:
        smtp_port = int(port or 465)
    except (ValueError, TypeError):
        smtp_port = 465

    smtp_user = username
    smtp_pass = password
    smtp_from = from_address or smtp_user

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
