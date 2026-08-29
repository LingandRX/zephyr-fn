"""邮件通知工具（Python 标准库 smtplib）。

纯基础设施：SMTP 参数一律由调用方传入（scheduler / 测试通知接口
从设置服务读取后传入），本模块不依赖任何存储层，保持分层纯净。
"""
from __future__ import annotations

import logging
import re
import smtplib
from email.header import Header
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

# 默认发件人地址
DEFAULT_FROM_ADDRESS = "subscription@localhost"

# 简单的邮箱格式验证正则
EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def _validate_email(address: str, field_name: str = "email") -> None:
    """验证邮箱地址格式。"""
    if not address or not EMAIL_PATTERN.match(address):
        raise ValueError(f"无效的 {field_name} 地址: {address}")


def send_email(
    to_address: str,
    subject: str,
    body: str,
    *,
    host: str | None = None,
    port: int | None = None,
    username: str | None = None,
    password: str | None = None,
    from_address: str | None = None,
) -> None:
    """通过 SMTP 发送单封文本邮件（host 必填）。

    Args:
        to_address: 收件人邮箱地址
        subject: 邮件主题
        body: 邮件正文（纯文本）
        host: SMTP 服务器地址（必填）
        port: SMTP 端口号，默认 465（SSL）
        username: SMTP 用户名
        password: SMTP 密码
        from_address: 发件人地址，默认使用 username 或 DEFAULT_FROM_ADDRESS

    Raises:
        RuntimeError: 未配置 SMTP 服务器
        ValueError: 邮箱地址格式无效或端口号无效
        smtplib.SMTPException: SMTP 连接或发送失败
    """
    # 验证 SMTP 服务器
    smtp_host = host
    if not smtp_host:
        raise RuntimeError("未配置 SMTP 服务器")

    # 验证端口号
    if port is not None:
        if not isinstance(port, int) or port < 1 or port > 65535:
            raise ValueError(f"无效的端口号: {port}，必须是 1-65535 之间的整数")
        smtp_port = port
    else:
        smtp_port = 465

    # 验证收件人地址
    _validate_email(to_address, "收件人")

    smtp_user = username
    smtp_pass = password
    smtp_from = from_address or smtp_user or DEFAULT_FROM_ADDRESS

    # 验证发件人地址
    _validate_email(smtp_from, "发件人")

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = smtp_from
    msg["To"] = to_address

    logger.info(f"准备发送邮件: from={smtp_from}, to={to_address}, host={smtp_host}:{smtp_port}")

    # 根据端口选择连接方式
    if smtp_port == 465:
        server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
    else:
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
        server.starttls()

    try:
        if smtp_user:
            server.login(smtp_user, smtp_pass or "")
        server.sendmail(smtp_from, [to_address], msg.as_string())
        logger.info(f"邮件发送成功: to={to_address}")
    except smtplib.SMTPException as e:
        logger.error(f"邮件发送失败: to={to_address}, error={e}")
        raise
    finally:
        try:
            server.quit()
        except smtplib.SMTPException as e:
            logger.warning(f"关闭 SMTP 连接时出错: {e}")
        except Exception as e:
            logger.warning(f"关闭 SMTP 连接时发生未知错误: {e}")
