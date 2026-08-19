"""后台定时任务：到期提醒和备份。"""
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

try:  # 包模式与直接从 backend 目录启动模式兼容。
    from . import backup as backup_service
    from . import config, db, email_sender, notifications, pushplus
except ImportError:  # pragma: no cover
    import backup as backup_service
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


def _fsync_directory(directory: Path) -> None:
    """尽力持久化目录项；Windows/部分文件系统不支持时不阻塞备份。"""
    try:
        fd = os.open(str(directory), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except (OSError, ValueError):
        pass


def _atomic_write_json(path: Path, data: dict) -> None:
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        encoded = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        with temp_path.open("wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        _fsync_directory(path.parent)
    finally:
        temp_path.unlink(missing_ok=True)


def _atomic_copy_database(temp_path: Path, target_path: Path) -> None:
    temp_path.unlink(missing_ok=True)
    try:
        db.export_db_copy(temp_path)
        # export_db_copy 关闭了目标 sqlite 连接后，重新打开只为 fsync 文件内容。
        with temp_path.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temp_path, target_path)
        _fsync_directory(target_path.parent)
    finally:
        temp_path.unlink(missing_ok=True)


def _backup_names(stamp: str, backup_dir: Path) -> tuple[Path, Path]:
    """生成不会因同秒并发而冲突的 JSON/DB 文件名。"""
    for _ in range(8):
        suffix = uuid.uuid4().hex[:8]
        json_file = backup_dir / f"subscription-backup-{stamp}-{suffix}.json"
        db_file = backup_dir / f"subscription-{stamp}-{suffix}.db"
        if not json_file.exists() and not db_file.exists():
            return json_file, db_file
    # UUID 冲突概率极低；最后一次仍返回唯一命名格式，写入采用 replace。
    suffix = uuid.uuid4().hex
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

    # 清理本次/历史失败留下的临时文件；不删除没有 JSON 配对的正式 DB，
    # 以免误删旧版本产生的可恢复备份。
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
    """执行备份并分别报告 JSON/SQLite 状态。

    - ``user_id=...``：只写该用户的 JSON；不生成 SQLite，因为 SQLite 文件副本
      天然包含全体用户，返回 ``db_ok=None`` 表示未请求 DB 备份。
    - ``include_all=True``：仅供后台内部任务或已授权管理员调用，写入 JSON + DB。
    - 无范围调用不再默认全量写盘，返回明确错误，等待主任务把身份传入。
    """
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
    settings = db.get_app_settings()
    if not settings.get("notification_enabled"):
        return
    if notifications.is_do_not_disturb(settings):
        return

    try:
        subs = notifications.get_subscriptions_needing_notification(
            reminder_days=reminder_days
        )
    except TypeError:
        # 兼容主任务尚未同步的新签名/替代 notifications stub。
        subs = notifications.get_subscriptions_needing_notification()
    if not subs:
        return

    for sub in subs:
        try:
            title, body = notifications.generate_notification_content(sub)
        except ValueError:
            continue
        _send_channels(settings, sub, title, body)


def _legacy_claim(subscription_id: str, channel: str) -> str | None:
    """notifications 模块尚未提供 claim API 时的兼容路径。"""
    try:
        if db.has_channel_notified_today(subscription_id, channel):
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
            db.log_notification(subscription_id, channel, status, error_message)
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

    # 系统日志渠道（NAS 上可通过日志查看；桌面系统通知由前端轮询展示）
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
                lambda: email_sender.send_email(to_address, title, body),
                f"已发送: {title}",
            )

    if settings.get("pushplus_enabled") and settings.get("pushplus_token"):
        _run_channel(
            sub_id,
            "pushplus",
            lambda: pushplus.send_pushplus(settings["pushplus_token"], title, body),
            f"已发送: {title}",
        )


# --------------------------------------------------------------------------- #
# 主循环
# --------------------------------------------------------------------------- #


def _loop(reminder_days: int | None) -> None:
    next_backup = 0.0
    while True:
        try:
            now = time.time()
            _check_reminders(reminder_days)
            if now >= next_backup:
                # 定时任务是内部系统调用，显式声明全量范围；HTTP 路由调用
                # backup_now() 则不会因为缺失身份而隐式生成全量文件。
                result = backup_now(include_all=True)
                if not result.get("ok"):
                    _logger().error("定时备份未完整完成: %s", result.get("error"))
                next_backup = now + BACKUP_INTERVAL
        except Exception:  # noqa: BLE001
            _logger().exception("定时任务执行出错")
        time.sleep(CHECK_INTERVAL)


def start_scheduler(reminder_days: int | None) -> threading.Thread:
    thread = threading.Thread(
        target=_loop, args=(reminder_days,), name="scheduler", daemon=True
    )
    thread.start()
    return thread
