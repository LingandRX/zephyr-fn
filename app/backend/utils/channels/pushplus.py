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
    payload = json.dumps({
        "token": token,
        "title": title,
        "content": content,
        "template": "html",
    }).encode("utf-8")
    req = urllib.request.Request(
        PUSHPLUS_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if body.get("code") != 200:
        raise RuntimeError(f"PushPlus 返回错误: {body.get('msg')}")