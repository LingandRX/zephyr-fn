"""后台定时任务调度服务：到期提醒和定期备份。

调度器运行在独立守护线程中，不持有请求上下文；每次循环迭代显式
``with app.app_context()`` 获取数据库会话（Flask-SQLAlchemy 会话按
上下文隔离，线程间互不串扰）。
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

from flask import Flask

from .. import config
from ..services import backup as backup_service
from ..services import notifications
from ..storage import repositories
from ..utils import channels
from ..utils.file_utils import atomic_write_json, fsync_directory

send_email = channels.send_email
send_pushplus = channels.send_pushplus


CHECK_INTERVAL = 3600          # 通知检查间隔 1 小时
BACKUP_INTERVAL = 24 * 3600    # 备份间隔 24 小时
KEEP_BACKUPS = 5               # 保留最近 5 份 JSON 备份
LOGGER_NAME = "subscription"


def _logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def _fsync_directory(directory: Path) -> None:
    fsync_directory(directory)


def _atomic_write_json(path: Path, data: dict) -> None:
    atomic_write_json(path, data)


def _atomic_copy_database(temp_path: Path, target_path: Path) -> None:
    temp_path.unlink(missing_ok=True)
    try:
        repositories.export_db_copy(temp_path)
        # r+b：Windows 上只读句柄不允许 fsync（Linux 允许），必须可写打开
        with temp_path.open("r+b") as handle:
            os.fsync(handle.fileno())
        os.replace(temp_path, target_path)
        fsync_directory(target_path.parent)
    finally:
        temp_path.unlink(missing_ok=True)


def _backup_names(stamp: str, backup_dir: Path) -> tuple[Path, Path]:
    """生成不会因同秒并发而冲突的 JSON/DB 文件名。"""
    suffix = uuid.uuid4().hex[:8]
    return (
        backup_dir / f"subscription-backup-{stamp}-{suffix}.json",
        backup_dir / f"subscription-{stamp}-{suffix}.db",
    )


def _db_name_for_json(json_name: str) -> str:
    stem = json_name[len("subscription-backup-"):-len(".json")]
    return f"subscription-{stem}.db"


def _prune(backup_dir: Path) -> None:
    """按 JSON 备份保留策略清理，并同步清理对应 DB 文件。"""
    try:
        json_files = sorted(
            backup_dir.glob("subscription-backup-*.json"),
            key=lambda path: (path.stat().st_mtime, path.name),
        )
    except OSError as exc:
        _logger().warning("读取备份目录失败，跳过清理: %s", exc)
        return

    if len(json_files) > KEEP_BACKUPS:
        for old in json_files[:-KEEP_BACKUPS]:
            try:
                old.unlink(missing_ok=True)
                (backup_dir / _db_name_for_json(old.name)).unlink(missing_ok=True)
            except OSError as exc:
                _logger().warning("清理旧备份失败 %s: %s", old, exc)

    for temp in backup_dir.glob(".*.tmp"):
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def _backup_error_result(backup_dir: Path, message: str, *, user_id: str | None,
                         include_all: bool) -> dict:
    db_requested = include_all
    return {
        "ok": False,
        "json_ok": False,
        "db_ok": False if db_requested else None,
        "json_success": False,
        "db_success": False if db_requested else None,
        "db_requested": db_requested,
        "file": None,
        "db_file": None,
        "count": 0,
        "backup_dir": str(backup_dir),
        "scope": {"user_id": user_id, "all_users": include_all},
        "errors": [message],
        "error": message,
    }


def backup_now(user_id: str | None = None, *, include_all: bool = False) -> dict:
    """执行备份并分别报告 JSON/SQLite 状态。"""
    backup_dir = config.backup_dir()
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _backup_error_result(
            backup_dir, f"创建备份目录失败: {exc}", user_id=user_id, include_all=include_all
        )

    if include_all and user_id not in (None, ""):
        return _backup_error_result(
            backup_dir, "user_id 与 include_all 不能同时使用",
            user_id=user_id, include_all=include_all,
        )
    if not include_all and not str(user_id or "").strip():
        return _backup_error_result(
            backup_dir, "备份必须明确指定 user_id；全量备份需显式 include_all=True",
            user_id=None, include_all=False,
        )

    scope_user = str(user_id).strip() if user_id not in (None, "") else None
    json_file, db_file = _backup_names(
        datetime.now().strftime("%Y%m%d-%H%M%S-%f"), backup_dir
    )
    errors: list[str] = []
    json_ok = False
    db_ok: bool | None = None if not include_all else False
    count = 0
    json_name: str | None = None
    db_name: str | None = None

    try:
        data = backup_service.export_json(scope_user, include_all=include_all)
        data["version"] = config.app_version()
        count = len(data.get("subscriptions") or [])
        _atomic_write_json(json_file, data)
        json_ok = True
        json_name = json_file.name
    except Exception as exc:  # noqa: BLE001
        errors.append(f"JSON 备份失败: {exc}")
        _logger().warning("JSON 备份失败: %s", exc)

    if include_all:
        try:
            temp_db = db_file.with_name(f".{db_file.name}.{uuid.uuid4().hex}.tmp")
            _atomic_copy_database(temp_db, db_file)
            db_ok = True
            db_name = db_file.name
        except Exception as exc:  # noqa: BLE001
            errors.append(f"SQLite 备份失败: {exc}")
            _logger().warning("复制数据库副本失败: %s", exc)

    _prune(backup_dir)
    ok = json_ok and (not include_all or db_ok is True)
    if ok:
        _logger().info("备份完成: %s (订阅 %d 条)", json_file, count)
    else:
        _logger().warning("备份未完整完成: json_ok=%s db_ok=%s", json_ok, db_ok)

    result = {
        "ok": ok,
        "json_ok": json_ok,
        "db_ok": db_ok,
        "json_success": json_ok,
        "db_success": db_ok,
        "db_requested": include_all,
        "file": json_name,
        "db_file": db_name,
        "count": count,
        "backup_dir": str(backup_dir),
        "scope": {"user_id": scope_user, "all_users": include_all},
        "errors": errors,
    }
    if errors:
        result["error"] = "; ".join(errors)
    return result


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
            _run_channel(
                sub_id,
                "email",
                lambda: send_email(
                    to_address, title, body,
                    host=settings.get("smtp_host"),
                    port=settings.get("smtp_port"),
                    username=settings.get("smtp_username"),
                    password=settings.get("smtp_password"),
                    from_address=settings.get("smtp_from_address"),
                ),
                f"已发送: {title}",
            )

    if settings.get("pushplus_enabled") and settings.get("pushplus_token"):
        _run_channel(
            sub_id,
            "pushplus",
            lambda: send_pushplus(settings["pushplus_token"], title, body),
            f"已发送: {title}",
        )


# --------------------------------------------------------------------------- #
# 主循环
# --------------------------------------------------------------------------- #

def _loop(app: Flask, reminder_days: int | None) -> None:
    next_backup = 0.0
    while True:
        try:
            with app.app_context():
                now = time.time()
                _check_reminders(reminder_days)
                if now >= next_backup:
                    result = backup_now(include_all=True)
                    if not result.get("ok"):
                        _logger().error("定时备份未完整完成: %s", result.get("error"))
                    next_backup = now + BACKUP_INTERVAL
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
