"""通知服务：免打扰判断、到期筛选、文案以及通知幂等领取。"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

try:  # 包模式与直接从 backend 目录启动模式兼容。
    from . import db, domain
except ImportError:  # pragma: no cover
    import db
    import domain


LOGGER_NAME = "subscription"
NOTIFICATION_CLAIM_TTL_SECONDS = 6 * 60 * 60
_VALID_NOTIFICATION_STATUSES = {"pending", "sent", "failed"}
_claim_lock = threading.RLock()
_memory_claims: set[tuple[str, str, str]] = set()


def _logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def _parse_clock(value: Any) -> int | None:
    """把 HH:MM 转成当天分钟数；非法配置返回 None。"""
    if value in (None, ""):
        return None
    text = str(value).strip()
    parts = text.split(":")
    if len(parts) != 2:
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except (TypeError, ValueError):
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour * 60 + minute


def is_do_not_disturb(settings: dict | None = None,
                      now: datetime | None = None) -> bool:
    """判断当前时间是否处于免打扰区间，精确到分钟并支持跨午夜。"""
    settings = settings if settings is not None else db.get_app_settings()
    start = _parse_clock(settings.get("do_not_disturb_start"))
    end = _parse_clock(settings.get("do_not_disturb_end"))
    if start is None or end is None or start == end:
        # 起止相同沿用旧语义：视为未配置，而不是全天免打扰。
        return False

    current = now or datetime.now()
    current_minutes = current.hour * 60 + current.minute
    if start < end:
        return start <= current_minutes < end
    return current_minutes >= start or current_minutes < end


def _reminder_days(settings: dict, override: int | None) -> int:
    value: Any = override if override is not None else settings.get("notification_days")
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        if override is not None:
            try:
                return max(0, int(settings.get("notification_days") or 7))
            except (TypeError, ValueError):
                return 7
        return 7


def get_subscriptions_needing_notification(
    user_id: str | None = None, reminder_days: int | None = None
) -> list[dict]:
    """返回提醒窗口内的订阅。

    ``reminder_days`` 是调度器显式传入的安装向导参数；未传入时继续使用
    app_settings.notification_days，保持旧调用兼容。
    """
    settings = db.get_app_settings()
    days = _reminder_days(settings, reminder_days)
    today = date.today()
    end_date = today + timedelta(days=days)

    if user_id is None:
        # 这是后台调度器的内部全量扫描，不向 HTTP 客户端直接返回。
        subs = db.get_all_subscriptions_raw()
    else:
        user = str(user_id).strip()
        if not user:
            return []
        subs = db.get_all_subscriptions(user)

    result = []
    for sub in subs:
        if sub.get("lifecycle") != "active":
            continue
        due = sub.get("next_due_date")
        if not due:
            continue
        try:
            due_text = str(due)
            if len(due_text) > 10 and due_text[10] in ("T", " "):
                due_text = due_text[:10]
            due_date = date.fromisoformat(due_text)
        except (TypeError, ValueError):
            continue
        if today <= due_date <= end_date:
            result.append(sub)
    result.sort(key=lambda item: (item.get("next_due_date") or "", item.get("name") or ""))
    return result


def generate_notification_content(sub: dict) -> tuple[str, str]:
    today = date.today()
    due_date = sub.get("next_due_date")
    if not due_date:
        raise ValueError("订阅缺少下次到期日")
    try:
        due_date = str(due_date)
        if len(due_date) > 10 and due_date[10] in ("T", " "):
            due_date = due_date[:10]
        due = date.fromisoformat(due_date)
    except (TypeError, ValueError) as exc:
        raise ValueError("下次到期日格式无效") from exc

    days_until = (due - today).days
    currency = str(sub.get("currency") or "CNY").upper()
    symbol = domain.CURRENCY_SYMBOLS.get(currency, "¥")
    try:
        amount = f"{symbol}{int(sub.get('amount') or 0) / 100:.2f}"
    except (TypeError, ValueError) as exc:
        raise ValueError("订阅金额格式无效") from exc

    name = str(sub.get("name") or "未命名订阅")
    title = f"{name} 今天到期" if days_until == 0 else f"{name} 将在 {days_until} 天后到期"
    body = f"金额: {amount}  到期日: {due.isoformat()}"
    return title, body


# --------------------------------------------------------------------------- #
# 通知幂等：优先使用 SQLite 事务领取，兼容旧 db API 时降级为进程锁
# --------------------------------------------------------------------------- #


def _conn_and_lock() -> tuple[Any, Any] | tuple[None, None]:
    conn = getattr(db, "_conn", None)
    lock = getattr(db, "_lock", None)
    if conn is None or lock is None:
        return None, None
    return conn, lock


def _parse_created_at(value: Any) -> float | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


def claim_notification(subscription_id: str, channel: str) -> str | None:
    """原子领取某订阅/渠道/当天的发送名额。

    返回 claim id；已有 sent 或近期 pending 时返回 None。SQLite 连接可用时使用
    ``BEGIN IMMEDIATE``，因此多个 scheduler 进程也不会同时通过 check-then-insert
    竞态。旧/替代 db 没有私有连接时使用进程内锁，并继续调用公开 API。
    """
    sub_id = str(subscription_id or "").strip()
    channel_name = str(channel or "").strip()
    if not sub_id or not channel_name:
        return None
    today = date.today().isoformat()
    key = (sub_id, channel_name, today)
    now = time.time()

    conn, lock = _conn_and_lock()
    if conn is not None:
        with _claim_lock, lock:
            started = False
            try:
                conn.execute("BEGIN IMMEDIATE")
                started = True
                row = conn.execute(
                    "SELECT id, status, created_at FROM notification_logs "
                    "WHERE subscription_id=? AND notification_date=? AND channel=? "
                    "ORDER BY created_at DESC LIMIT 1",
                    (sub_id, today, channel_name),
                ).fetchone()
                if row:
                    status = str(row[1] or "")
                    if status == "sent":
                        conn.rollback()
                        return None
                    if status == "pending":
                        created = _parse_created_at(row[2])
                        if created is None or now - created < NOTIFICATION_CLAIM_TTL_SECONDS:
                            conn.rollback()
                            return None
                        # 旧进程可能已经崩溃，允许超时重试，同时留下失败痕迹。
                        conn.execute(
                            "UPDATE notification_logs SET status='failed', "
                            "error_message=? WHERE id=?",
                            ("notification claim expired", row[0]),
                        )
                claim_id = db.new_id()
                cursor = conn.execute(
                    "INSERT INTO notification_logs "
                    "(id, subscription_id, notification_date, channel, status, "
                    "error_message, created_at) VALUES (?,?,?,?,?,?,?) "
                    "ON CONFLICT(subscription_id, notification_date, channel) DO UPDATE SET "
                    "id=excluded.id, status='pending', error_message=NULL, "
                    "created_at=excluded.created_at "
                    "WHERE notification_logs.status <> 'sent'",
                    (claim_id, sub_id, today, channel_name, "pending", None, db.now_utc()),
                )
                if cursor.rowcount == 0:
                    # 另一个领取者已经把该 identity 发送成功；不能覆盖 sent。
                    conn.rollback()
                    return None
                conn.commit()
                return claim_id
            except Exception:  # noqa: BLE001
                if started:
                    try:
                        conn.rollback()
                    except Exception:  # noqa: BLE001
                        pass
                # 连接正在迁移/替代 db 实现异常时，继续走公开 API 兼容路径。

    with _claim_lock:
        if key in _memory_claims:
            return None
        try:
            if db.has_channel_notified_today(sub_id, channel_name):
                return None
        except Exception:  # noqa: BLE001
            # 没有查询能力时，进程锁仍能阻止同一进程内重复发送。
            pass
        _memory_claims.add(key)
        return f"memory:{sub_id}:{channel_name}:{today}"


def complete_notification(claim_id: str | None, subscription_id: str, channel: str,
                          status: str, error_message: str | None = None) -> None:
    """完成/失败一个 claim；兼容旧 db API。"""
    if status not in _VALID_NOTIFICATION_STATUSES or status == "pending":
        status = "failed"
    sub_id = str(subscription_id or "").strip()
    channel_name = str(channel or "").strip()
    claim = str(claim_id or "")
    today = date.today().isoformat()

    if claim.startswith("memory:"):
        with _claim_lock:
            _memory_claims.discard((sub_id, channel_name, today))
        try:
            db.log_notification(sub_id, channel_name, status, error_message)
        except Exception:  # noqa: BLE001
            _logger().exception("写入通知日志失败: %s/%s", sub_id, channel_name)
        return

    conn, lock = _conn_and_lock()
    if conn is not None and claim:
        try:
            with _claim_lock, lock:
                cursor = conn.execute(
                    "UPDATE notification_logs SET status=?, error_message=? WHERE id=?",
                    (status, error_message, claim),
                )
                conn.commit()
                if cursor.rowcount:
                    return
        except Exception:  # noqa: BLE001
            _logger().exception("更新通知 claim 失败: %s", claim)

    # claim 不是当前 db 连接创建的，或兼容实现没有事务表，至少保留公开日志。
    try:
        db.log_notification(sub_id, channel_name, status, error_message)
    except Exception:  # noqa: BLE001
        _logger().exception("写入通知日志失败: %s/%s", sub_id, channel_name)


# 便于主任务在不同命名约定下整合。
finish_notification = complete_notification
