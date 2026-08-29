"""后台定时任务调度服务：到期提醒。

调度器运行在独立守护线程中，不持有请求上下文；每次循环迭代显式
``with app.app_context()`` 获取数据库会话（Flask-SQLAlchemy 会话按
上下文隔离，线程间互不串扰）。
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from flask import Flask

from ..services import notifications
from ..storage import repositories
from ..utils import channels

send_email = channels.send_email
send_pushplus = channels.send_pushplus


CHECK_INTERVAL = 3600          # 通知检查间隔 1 小时
LOGGER_NAME = "subscription"


def _logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


# --------------------------------------------------------------------------- #
# 到期提醒
# --------------------------------------------------------------------------- #

def _check_reminders(reminder_days: int | None = None) -> None:
    settings = repositories.get_app_settings()
    if not settings.get("notification_enabled"):
        return
    if notifications.is_do_not_disturb(settings):
        return

    try:
        subs = notifications.get_subscriptions_needing_notification(
            reminder_days=reminder_days
        )
    except TypeError:
        subs = notifications.get_subscriptions_needing_notification()
    if not subs:
        return

    for i, sub in enumerate(subs):
        try:
            title, body = notifications.generate_notification_content(sub)
        except ValueError:
            continue
        _send_channels(settings, sub, title, body)
        if i < len(subs) - 1:
            time.sleep(1)


def _legacy_claim(subscription_id: str, channel: str) -> str | None:
    try:
        if notifications.has_channel_notified_today(subscription_id, channel):
            return None
    except Exception:  # noqa: BLE001
        pass
    return f"legacy:{subscription_id}:{channel}"


def _complete_claim(claim_id: str | None, subscription_id: str, channel: str,
                    status: str, error_message: str | None = None) -> None:
    complete = getattr(notifications, "complete_notification", None)
    if callable(complete):
        complete(claim_id, subscription_id, channel, status, error_message)
        return
    if claim_id and claim_id.startswith("legacy:"):
        try:
            notifications.log_notification(subscription_id, channel, status, error_message)
        except Exception:  # noqa: BLE001
            _logger().exception("写入通知日志失败: %s/%s", subscription_id, channel)


def _run_channel(sub_id: str, channel: str, sender: Callable[[], None],
                 success_log: str) -> None:
    claim = getattr(notifications, "claim_notification", None)
    claim_id = claim(sub_id, channel) if callable(claim) else _legacy_claim(sub_id, channel)
    if not claim_id:
        return
    try:
        sender()
    except Exception as exc:  # noqa: BLE001
        _complete_claim(claim_id, sub_id, channel, "failed", str(exc))
        _logger().warning("到期提醒 [%s] 发送失败: %s", channel, exc)
    else:
        _complete_claim(claim_id, sub_id, channel, "sent")
        _logger().info("到期提醒 [%s] %s", channel, success_log)


def _send_channels(settings: dict, sub: dict, title: str, body: str) -> None:
    sub_id = str(sub["id"])

    # 系统日志渠道
    _run_channel(
        sub_id,
        "system",
        lambda: _logger().info("到期提醒 [system] %s: %s — %s", title, body, sub_id),
        f"已记录: {title}",
    )

    if settings.get("email_enabled") and settings.get("smtp_host"):
        to_address = settings.get("smtp_username") or settings.get("smtp_from_address")
        if to_address:
            # 确保 port 为整数
            port_raw = settings.get("smtp_port")
            try:
                port = int(port_raw) if port_raw is not None else 465
            except (ValueError, TypeError):
                port = 465
            _run_channel(
                sub_id,
                "email",
                lambda: send_email(
                    to_address, title, body,
                    host=settings.get("smtp_host"),
                    port=port,
                    username=settings.get("smtp_username"),
                    password=settings.get("smtp_password"),
                    from_address=settings.get("smtp_from_address"),
                ),
                f"已发送: {title}",
            )

    if settings.get("pushplus_enabled") and settings.get("pushplus_token"):
        # PushPlus 专用 SMTP 配置（优先），回退到通用 SMTP
        pp_smtp_host = settings.get("pushplus_smtp_host") or settings.get("smtp_host")
        pp_port_raw = settings.get("pushplus_smtp_port") or settings.get("smtp_port")
        try:
            pp_port = int(pp_port_raw) if pp_port_raw is not None else 465
        except (ValueError, TypeError):
            pp_port = 465
        pp_username = settings.get("pushplus_smtp_username") or settings.get("smtp_username")
        pp_password = settings.get("pushplus_smtp_password") or settings.get("smtp_password")
        pp_from_address = settings.get("pushplus_smtp_from_address") or settings.get("smtp_from_address")

        _run_channel(
            sub_id,
            "pushplus",
            lambda: send_pushplus(
                settings["pushplus_token"], title, body,
                host=pp_smtp_host,
                port=pp_port,
                username=pp_username,
                password=pp_password,
                from_address=pp_from_address,
            ),
            f"已发送: {title}",
        )


# --------------------------------------------------------------------------- #
# 主循环
# --------------------------------------------------------------------------- #

def _loop(app: Flask, reminder_days: int | None) -> None:
    while True:
        try:
            with app.app_context():
                _check_reminders(reminder_days)
        except Exception:  # noqa: BLE001
            _logger().exception("定时任务执行出错")
        time.sleep(CHECK_INTERVAL)


def start_scheduler(app: Flask, reminder_days: int | None = None) -> threading.Thread:
    """启动后台调度线程；调用方需传入应用实例（工厂产物）。"""
    thread = threading.Thread(
        target=_loop, args=(app, reminder_days), name="scheduler", daemon=True
    )
    thread.start()
    return thread