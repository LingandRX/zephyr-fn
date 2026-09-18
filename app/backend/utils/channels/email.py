"""邮件通知工具（Python 标准库 smtplib）。

纯基础设施：SMTP 参数一律由调用方传入（scheduler / 测试通知接口
从设置服务读取后传入），本模块不依赖任何存储层，保持分层纯净。
"""

from __future__ import annotations

import logging
import re
import smtplib
import socket
import ssl
from email.header import Header
from email.mime.multipart import MIMEMultipart
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
    body_html: str | None = None,
    host: str | None = None,
    port: int | None = None,
    username: str | None = None,
    password: str | None = None,
    from_address: str | None = None,
) -> None:
    """通过 SMTP 发送单封邮件（host 必填，支持纯文本或 HTML 多部件）。

    Args:
        to_address: 收件人邮箱地址
        subject: 邮件主题
        body: 邮件正文（纯文本）
        body_html: 邮件正文（HTML，可选）
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

    if body_html:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"] = smtp_from
        msg["To"] = to_address
        msg.attach(MIMEText(body, "plain", "utf-8"))
        msg.attach(MIMEText(body_html, "html", "utf-8"))
    else:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"] = smtp_from
        msg["To"] = to_address

    logger.info(
        "准备发送邮件: from=%s, to=%s, host=%s:%s", smtp_from, to_address, smtp_host, smtp_port
    )

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
        logger.info("邮件发送成功: to=%s", to_address)
    except smtplib.SMTPException as e:
        logger.error("邮件发送失败: to=%s, error=%s", to_address, e)
        raise
    finally:
        try:
            server.quit()
        except smtplib.SMTPException as e:
            logger.warning("关闭 SMTP 连接时出错: %s", e)
        except Exception as e:
            logger.warning("关闭 SMTP 连接时发生未知错误: %s", e)


def format_email_error(exc: Exception) -> str:
    """将邮件发送过程中的底层异常转换为清晰、友好、具有操作指导的中文提示。"""
    if exc is None:
        return "邮件发送失败: 未知错误"

    err_str = str(exc)

    # 1. 处理 smtplib.SMTPRecipientsRefused (收件人拒收)
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        details = []
        for r_addr, r_err in getattr(exc, "recipients", {}).items():
            r_msg = r_err[1] if isinstance(r_err, (tuple, list)) and len(r_err) > 1 else str(r_err)
            if isinstance(r_msg, bytes):
                r_msg = r_msg.decode("utf-8", errors="ignore").strip()
            details.append(f"{r_addr}: {r_msg}")
        joined = f" ({'; '.join(details)})" if details else ""
        return f"收件人邮箱被拒绝接收（550）：请检查收件邮箱地址是否存在或正确{joined}"

    # 2. 处理 SMTPResponseException 及其子类 (SMTPSenderRefused, SMTPAuthenticationError 等)
    if isinstance(exc, smtplib.SMTPResponseException) or hasattr(exc, "smtp_code"):
        code = getattr(exc, "smtp_code", None)
        raw_msg = getattr(exc, "smtp_error", "")
        if isinstance(raw_msg, bytes):
            raw_text = raw_msg.decode("utf-8", errors="ignore").strip()
        else:
            raw_text = str(raw_msg).strip()

        raw_lower = raw_text.lower()

        # 503: 未鉴权 / 顺序错误 (EHLO and AUTH first)
        if code == 503 or "need ehlo and auth first" in raw_lower or "auth first" in raw_lower:
            return (
                "SMTP 身份验证失败（503）：邮件服务器要求必须先完成登录认证（AUTH）。"
                "请检查是否已填写「SMTP 用户名」与「密码/授权码」（注意：QQ 邮箱、网易邮箱等需使用专用的客户端授权码，而非登录密码）。"
            )

        # 535 / 534: 认证失败（密码/授权码或用户名错误）
        if (
            code in (535, 534)
            or isinstance(exc, smtplib.SMTPAuthenticationError)
            or "authentication failed" in raw_lower
            or "login fail" in raw_lower
            or "system forbidden" in raw_lower
        ):
            return (
                "SMTP 登录认证失败（535）：用户名或密码/授权码错误。"
                "注意：QQ 邮箱、163/126 邮箱、Gmail 等必须在邮箱网页版设置中开启 POP3/SMTP 服务，并使用专属的「授权码/应用密码」登录。"
            )

        # 530: 必须使用 STARTTLS 或未登录
        if code == 530 or "starttls" in raw_lower or "must issue a starttls" in raw_lower:
            return (
                "SMTP 连接安全策略不符（530）：服务器要求加密传输或身份验证。"
                "请检查 SMTP 端口配置（SSL 加密推荐 465 端口，STARTTLS 推荐 587 端口），并确保填写了用户名和密码。"
            )

        # 550: 邮箱不存在或拒绝接收
        if code == 550 or "mailbox unavailable" in raw_lower or "user not found" in raw_lower:
            return f"收件人邮箱无效或拒收（550）：目标邮箱不存在或拒绝接收（{raw_text}）。请核对收件地址。"

        # 553: 发件人地址不一致或未授权中继
        if (
            code == 553
            or "must equal authorized user" in raw_lower
            or "relay access denied" in raw_lower
            or "sender address rejected" in raw_lower
        ):
            return (
                f"发件人地址被拒绝（553）：{raw_text}。"
                "提示：绝大多数国内邮件服务商（如 QQ、163、阿里云邮）要求「发件人地址」必须与登录认证的「SMTP 用户名」完全一致。"
            )

        # 554: 触发垃圾邮件拦截或事务失败
        if (
            code == 554
            or "spam" in raw_lower
            or "reject by content" in raw_lower
            or "transaction failed" in raw_lower
        ):
            return f"邮件被服务器拒绝（554）：触发反垃圾邮件规则或发信频次过高（{raw_text}）。请检查邮件内容或稍后再试。"

        # 501 / 502: 语法或参数错误
        if code in (501, 502) or "syntax error" in raw_lower:
            return f"SMTP 命令参数格式错误（{code}）：{raw_text}。请检查发件人或收件人邮箱格式是否规范。"

        # 421 / 450 / 451: 服务器繁忙或超限
        if code in (421, 450, 451):
            return f"SMTP 服务器繁忙或超限（{code}）：{raw_text}。请稍后重试。"

        # 兜底 SMTPResponseException
        clean_msg = raw_text or err_str
        clean_msg = re.sub(r"b['\"](.*?)['\"]", r"\1", clean_msg)
        return f"SMTP 服务器返回错误（{code or '未知'}）：{clean_msg}"

    # 3. 连接断开异常
    if isinstance(exc, smtplib.SMTPServerDisconnected):
        return (
            "与 SMTP 服务器的连接意外中断：通常由于端口与加密方式不匹配（例如在 465 端口未启用 SSL，或在 25/587 端口启用了 SSL），"
            "或服务器主动关闭了未认证的连接。建议核对端口配置（QQ/163 推荐 465 端口并使用 SSL）。"
        )

    # 4. 连接超时
    if isinstance(exc, (TimeoutError, socket.timeout)) or "timed out" in err_str.lower():
        return "连接 SMTP 服务器超时：请检查服务器地址和端口是否正确。若运行在云服务器（如阿里云、腾讯云），请注意服务商可能已封禁邮件常用端口。"

    # 5. 连接被拒绝
    if isinstance(exc, ConnectionRefusedError) or "connection refused" in err_str.lower():
        return "SMTP 服务器拒绝连接：目标主机未开放此端口或服务未运行，请检查服务器地址与端口号。"

    # 6. DNS 域名解析错误
    if (
        isinstance(exc, socket.gaierror)
        or "nodename nor servname provided" in err_str.lower()
        or "name or service not known" in err_str.lower()
    ):
        return (
            "SMTP 服务器域名解析失败：无法找到该服务器，请检查服务器地址拼写（例如 smtp.qq.com）。"
        )

    # 7. SSL / TLS 握手错误
    if (
        isinstance(exc, ssl.SSLError)
        or "wrong version number" in err_str.lower()
        or "certificate" in err_str.lower()
    ):
        return f"SSL/TLS 加密握手失败：端口与加密协议可能不匹配（465 端口通常为 SSL 加密，587/25 为 STARTTLS）。({err_str})"

    # 8. 参数与业务校验错误
    if isinstance(exc, (ValueError, RuntimeError)):
        return str(exc)

    # 9. 兜底清洗：若文本中含有形如 (503, b'...', '...')，做模式识别与字符串清洗
    err_lower = err_str.lower()
    if "need ehlo and auth first" in err_lower or "auth first" in err_lower:
        return (
            "SMTP 身份验证失败（503）：邮件服务器要求必须先完成登录认证（AUTH）。"
            "请检查是否已填写「SMTP 用户名」与「密码/授权码」（注意：QQ 邮箱、网易邮箱等需使用专用的客户端授权码，而非登录密码）。"
        )
    if "authentication failed" in err_lower or "login fail" in err_lower:
        return (
            "SMTP 登录认证失败（535）：用户名或密码/授权码错误。"
            "注意：QQ 邮箱、163/126 邮箱、Gmail 等必须在邮箱网页版设置中开启 POP3/SMTP 服务，并使用专属的「授权码/应用密码」登录。"
        )

    cleaned = err_str
    cleaned = re.sub(r"b['\"](.*?)['\"]", r"\1", cleaned)
    cleaned = re.sub(r"^\(\s*(\d+)\s*,\s*'(.*?)'\s*(?:,\s*'.*?')?\s*\)$", r"\1: \2", cleaned)
    return f"邮件发送失败: {cleaned}"
