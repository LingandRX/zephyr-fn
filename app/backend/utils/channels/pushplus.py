"""PushPlus 微信推送工具（标准库 urllib）。"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

PUSHPLUS_URL = "https://www.pushplus.plus/send"


def send_pushplus(
    token: str,
    title: str,
    content: str,
    *,
    host: str | None = None,
    port: int | None = None,
    username: str | None = None,
    password: str | None = None,
    from_address: str | None = None,
) -> None:
    """通过 PushPlus 发送消息。

    如果提供了 SMTP 配置（host），则通过邮件方式发送到 {token}@yp9.cn；
    否则使用 PushPlus HTTP API。
    """
    # 如果提供了 SMTP 配置，使用邮件方式
    if host:
        from .email import send_email

        to_address = f"{token}@yp9.cn"
        send_email(
            to_address=to_address,
            subject=title,
            body=content,
            host=host,
            port=port,
            username=username,
            password=password,
            from_address=from_address,
        )
        return

    # 否则使用 HTTP API
    payload = json.dumps(
        {
            "token": token,
            "title": title,
            "content": content,
            "template": "html",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        PUSHPLUS_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if body.get("code") != 200:
        code = body.get("code")
        msg = body.get("msg") or "未知错误"
        if code == 900:
            raise RuntimeError(
                f"PushPlus 推送失败（900）：Token 无效或未关注「PushPlus推送加」微信公众号（{msg}）"
            )
        elif code == 903:
            raise RuntimeError(f"PushPlus 推送失败（903）：今日推送次数已达上限或积分不足（{msg}）")
        elif code == 999:
            raise RuntimeError(f"PushPlus 服务端系统异常（999）：{msg}，请稍后重试")
        else:
            raise RuntimeError(f"PushPlus 返回错误（{code}）：{msg}")


def format_pushplus_error(exc: Exception) -> str:
    """将 PushPlus 发送异常转换为清晰友好的中文提示。"""
    if exc is None:
        return "PushPlus 推送失败: 未知错误"

    import smtplib
    import urllib.error

    from .email import format_email_error

    if isinstance(exc, (smtplib.SMTPException, ConnectionRefusedError)):
        return f"PushPlus 邮件通道错误: {format_email_error(exc)}"

    if isinstance(exc, urllib.error.HTTPError):
        return f"PushPlus 接口网络请求失败（HTTP {exc.code}）：{exc.reason}"
    if isinstance(exc, urllib.error.URLError):
        return f"PushPlus 服务器连接失败：{exc.reason}"
    if isinstance(exc, TimeoutError) or "timed out" in str(exc).lower():
        return "连接 PushPlus 服务器超时，请检查网络或稍后再试"

    return str(exc)
