"""后台定时任务调度服务：到期提醒。

调度器运行在独立守护线程中，不持有请求上下文；每次循环迭代显式
``with app.app_context()`` 获取数据库会话（Flask-SQLAlchemy 会话按
上下文隔离，线程间互不串扰）。
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from flask import Flask

from .. import repositories
from ..services import notifications
from ..utils import channels
from ..utils.channels.email import EMAIL_PATTERN

send_email = channels.send_email
send_pushplus = channels.send_pushplus
render_email_template = channels.render_email_template


DEFAULT_PUSH_TIME = "09:00"  # 每日固定推送时刻默认值（24h 制 HH:MM）
LOGGER_NAME = "subscription"

# 优雅停机控制：set() 时调度线程退出
_stop_event = threading.Event()
_scheduler_thread: threading.Thread | None = None
_scheduler_lock = threading.Lock()


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

    subs = notifications.get_subscriptions_needing_notification(reminder_days=reminder_days)
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


def _check_template_auto_sync() -> None:
    settings = repositories.get_app_settings()
    if not settings.get("template_auto_sync"):
        return
    url = (settings.get("template_sync_url") or "").strip()
    if not url:
        return

    last_synced = settings.get("template_last_synced_at")
    should_sync = False
    if not last_synced:
        should_sync = True
    else:
        try:
            last_dt = datetime.fromisoformat(last_synced.replace("Z", "+00:00"))
            now_dt = datetime.now(timezone.utc)
            if (now_dt - last_dt).total_seconds() >= 7 * 86400:
                should_sync = True
        except Exception:
            should_sync = True

    if should_sync:
        try:
            from . import templates as templates_service
            templates_service.sync_remote_templates()
            _logger().info("后台自动同步远程订阅模板成功")
        except Exception as err:
            _logger().warning("后台自动同步远程订阅模板失败: %s", err)


def _run_channel(sub_id: str, channel: str, sender: Callable[[], None], success_log: str) -> None:
    claim_id = notifications.claim_notification(sub_id, channel)
    if not claim_id:
        return
    try:
        sender()
    except (ValueError, RuntimeError) as exc:
        # 永久性失败（配置错误）：记录为 abandoned，不再重试
        notifications.complete_notification(claim_id, sub_id, channel, "abandoned", str(exc))
        _logger().warning("到期提醒 [%s] 配置错误，已标记为废弃: %s", channel, exc)
    except Exception as exc:  # noqa: BLE001
        # 暂时性失败（网络/SMTP 错误）：记录为 failed，下次可重试
        err_msg = channels.format_email_error(exc) if channel == "email" else str(exc)
        notifications.complete_notification(claim_id, sub_id, channel, "failed", err_msg)
        _logger().warning("到期提醒 [%s] 发送失败（将重试）: %s", channel, err_msg)
    else:
        notifications.complete_notification(claim_id, sub_id, channel, "sent")
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
            email_tpl = settings.get("email_template") or "default"
            mail_subject, mail_text, mail_html = render_email_template(email_tpl, sub)
            mail_user = settings.get("smtp_username") or settings.get("smtp_from_address")
            mail_from = settings.get("smtp_from_address") or settings.get("smtp_username")
            _run_channel(
                sub_id,
                "email",
                lambda: send_email(
                    to_address,
                    mail_subject,
                    mail_text,
                    body_html=mail_html,
                    host=settings.get("smtp_host"),
                    port=port,
                    username=mail_user,
                    password=settings.get("smtp_password"),
                    from_address=mail_from,
                ),
                f"已发送: {mail_subject}",
            )

    if settings.get("pushplus_enabled") and settings.get("pushplus_token"):
        # PushPlus 专用 SMTP 配置（优先），回退到通用 SMTP
        pp_smtp_host = settings.get("pushplus_smtp_host") or settings.get("smtp_host")
        pp_port_raw = settings.get("pushplus_smtp_port") or settings.get("smtp_port")
        try:
            pp_port = int(pp_port_raw) if pp_port_raw is not None else 465
        except (ValueError, TypeError):
            pp_port = 465
        pp_username = (
            settings.get("pushplus_smtp_username")
            or settings.get("smtp_username")
            or settings.get("pushplus_smtp_from_address")
            or settings.get("smtp_from_address")
        )
        pp_password = settings.get("pushplus_smtp_password") or settings.get("smtp_password")
        pp_from_address = (
            settings.get("pushplus_smtp_from_address")
            or settings.get("smtp_from_address")
            or pp_username
        )

        # PushPlus SMTP 模式：host 有值时走邮件通道，需预校验发件人地址
        if pp_smtp_host:
            pp_sender = pp_from_address or pp_username or ""
            if not pp_sender or not EMAIL_PATTERN.match(pp_sender):
                # 配置无效：直接抛 ValueError，由 _run_channel 标记为 abandoned
                def _raise_pp_config_error() -> None:
                    raise ValueError(f"无效的 PushPlus 发件人地址: {pp_sender or '未配置'}")

                _run_channel(sub_id, "pushplus", _raise_pp_config_error, "配置错误")
            else:
                _run_channel(
                    sub_id,
                    "pushplus",
                    lambda: send_pushplus(
                        settings["pushplus_token"],
                        title,
                        body,
                        host=pp_smtp_host,
                        port=pp_port,
                        username=pp_username,
                        password=pp_password,
                        from_address=pp_from_address,
                    ),
                    f"已发送: {title}",
                )
        else:
            # 无 SMTP host，走 PushPlus HTTP API
            _run_channel(
                sub_id,
                "pushplus",
                lambda: send_pushplus(
                    settings["pushplus_token"],
                    title,
                    body,
                ),
                f"已发送: {title}",
            )


# --------------------------------------------------------------------------- #
# 主循环
# --------------------------------------------------------------------------- #


def seconds_until_next_push(now: datetime, clock_text: str | None) -> float:
    """返回距离下一次本地时间 clock_text（HH:MM）的秒数。

    clock_text 为空/非法时回退到默认推送时刻；恰好等于该时刻时
    视为已过，顺延到明天同一时刻。
    """
    minutes = notifications.parse_clock(clock_text)
    if minutes is None:
        minutes = notifications.parse_clock(DEFAULT_PUSH_TIME)
    target = now.replace(hour=minutes // 60, minute=minutes % 60, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return max(0.0, (target - now).total_seconds())


def _next_delay(app: Flask) -> float:
    """读取推送时刻配置并计算到下一个触发点的等待秒数。"""
    try:
        with app.app_context():
            clock_text = repositories.get_app_settings().get("notification_time")
    except Exception:  # noqa: BLE001
        _logger().exception("读取推送时刻配置失败，使用默认 %s", DEFAULT_PUSH_TIME)
        clock_text = DEFAULT_PUSH_TIME
    return seconds_until_next_push(datetime.now(), clock_text)


def _loop(app: Flask, reminder_days: int | None) -> None:
    # 启动后先等一轮再执行（不立即触发）
    _next_fire = datetime.now() + timedelta(seconds=_next_delay(app))
    while not _stop_event.is_set():
        now = datetime.now()
        if now >= _next_fire:
            try:
                with app.app_context():
                    _check_reminders(reminder_days)
                    _check_template_auto_sync()
            except Exception:  # noqa: BLE001
                _logger().exception("定时任务执行出错")
            # 计算下一个推送时刻（读取最新配置，允许配置变更实时生效）
            _next_fire = datetime.now() + timedelta(seconds=_next_delay(app))
        else:
            # 短轮询：每 60 秒检查一次是否已到推送时刻
            _stop_event.wait(60)


def start_scheduler(app: Flask, reminder_days: int | None = None) -> threading.Thread:
    """启动后台调度线程；调用方需传入应用实例（工厂产物）。"""
    global _stop_event, _scheduler_thread
    with _scheduler_lock:
        _stop_event.clear()  # 允许 stop_scheduler 后重启
        thread = threading.Thread(
            target=_loop, args=(app, reminder_days), name="scheduler", daemon=True
        )
        _scheduler_thread = thread
        thread.start()
        return thread


def stop_scheduler(timeout: float = 10.0) -> None:
    """通知调度线程优雅退出（最多等待 timeout 秒）。"""
    global _scheduler_thread
    with _scheduler_lock:
        _logger().info("正在停止调度器...")
        _stop_event.set()
        if _scheduler_thread is not None and _scheduler_thread.is_alive():
            _scheduler_thread.join(timeout=timeout)
        _scheduler_thread = None
