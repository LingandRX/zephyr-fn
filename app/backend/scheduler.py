"""后台定时任务（守护线程，移植自 zephyr-tarui 的 scheduler.rs）：

1. 到期提醒 —— 每小时检查一次；对「今日 ~ 今日+notification_days 天内到期」的活跃订阅，
   按已启用的渠道（系统日志 / 邮件 / PushPlus）发送通知，每个订阅每天每渠道只发一次。
2. 自动备份 —— 每天把 JSON 导出 + SQLite 文件副本写入备份目录（data-share 共享目录）。
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path

import config
import db
import email_sender
import notifications
import pushplus

CHECK_INTERVAL = 3600          # 通知检查间隔 1 小时
BACKUP_INTERVAL = 24 * 3600    # 备份间隔 24 小时
KEEP_BACKUPS = 5               # 保留最近 5 份 JSON 备份
LOGGER_NAME = "subscription"


def _logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def backup_now() -> dict:
    """立即执行一次备份：JSON 导出 + SQLite 文件副本。"""
    backup_dir = config.backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    data = {
        "app": "subscription-manager",
        "version": config.app_version(),
        "exported_at": db.now_utc(),
        "categories": db.get_all_categories_raw(),
        "subscriptions": db.get_all_subscriptions_raw(),
    }
    json_file = backup_dir / f"subscription-backup-{stamp}.json"
    json_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    db_file = backup_dir / f"subscription-{stamp}.db"
    try:
        db.export_db_copy(db_file)
    except Exception as exc:  # noqa: BLE001
        _logger().warning("复制数据库副本失败: %s", exc)

    _prune(backup_dir)
    count = len(data["subscriptions"])
    _logger().info("备份完成: %s (订阅 %d 条)", json_file, count)
    return {
        "ok": True,
        "file": json_file.name,
        "count": count,
        "backup_dir": str(backup_dir),
    }


def _prune(backup_dir: Path) -> None:
    json_files = sorted(backup_dir.glob("subscription-backup-*.json"))
    for old in json_files[:-KEEP_BACKUPS]:
        old.unlink(missing_ok=True)
        base = old.name.replace("subscription-backup-", "subscription-").replace(".json", ".db")
        (backup_dir / base).unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# 到期提醒
# --------------------------------------------------------------------------- #

def _check_reminders() -> None:
    settings = db.get_app_settings()
    if not settings.get("notification_enabled"):
        return
    if notifications.is_do_not_disturb():
        return

    subs = notifications.get_subscriptions_needing_notification()
    if not subs:
        return

    for sub in subs:
        try:
            title, body = notifications.generate_notification_content(sub)
        except ValueError:
            continue
        _send_channels(settings, sub, title, body)


def _send_channels(settings: dict, sub: dict, title: str, body: str) -> None:
    sub_id = sub["id"]

    # 系统日志渠道（NAS 上可通过日志查看；桌面系统通知由前端轮询展示）
    if not db.has_channel_notified_today(sub_id, "system"):
        _logger().info("到期提醒 [system] %s: %s — %s", title, body, sub_id)
        db.log_notification(sub_id, "system", "sent")

    if settings.get("email_enabled") and settings.get("smtp_host"):
        if not db.has_channel_notified_today(sub_id, "email"):
            to_address = settings.get("smtp_username") or settings.get("smtp_from_address")
            if to_address:
                try:
                    email_sender.send_email(to_address, title, body)
                    db.log_notification(sub_id, "email", "sent")
                    _logger().info("到期提醒 [email] 已发送: %s", title)
                except Exception as exc:  # noqa: BLE001
                    db.log_notification(sub_id, "email", "failed", str(exc))
                    _logger().warning("邮件发送失败: %s", exc)

    if settings.get("pushplus_enabled") and settings.get("pushplus_token"):
        if not db.has_channel_notified_today(sub_id, "pushplus"):
            try:
                pushplus.send_pushplus(settings["pushplus_token"], title, body)
                db.log_notification(sub_id, "pushplus", "sent")
                _logger().info("到期提醒 [pushplus] 已发送: %s", title)
            except Exception as exc:  # noqa: BLE001
                db.log_notification(sub_id, "pushplus", "failed", str(exc))
                _logger().warning("PushPlus 发送失败: %s", exc)


# --------------------------------------------------------------------------- #
# 主循环
# --------------------------------------------------------------------------- #

def _loop(reminder_days: int) -> None:
    next_backup = 0.0
    while True:
        try:
            now = time.time()
            _check_reminders()
            if now >= next_backup:
                backup_now()
                next_backup = now + BACKUP_INTERVAL
        except Exception:  # noqa: BLE001
            _logger().exception("定时任务执行出错")
        time.sleep(CHECK_INTERVAL)


def start_scheduler(reminder_days: int) -> threading.Thread:
    thread = threading.Thread(
        target=_loop, args=(reminder_days,), name="scheduler", daemon=True
    )
    thread.start()
    return thread
