"""PushPlus 微信推送工具（标准库 urllib）。"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

PUSHPLUS_URL = "https://www.pushplus.plus/send"


def send_pushplus(token: str, title: str, content: str) -> None:
    """通过 PushPlus API 发送微信消息。"""
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
