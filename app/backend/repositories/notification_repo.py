"""通知日志仓储：通知幂等领取、邮件日志、通知结果记录。

领取（claim）使用 SQLite UPSERT 实现原子性；
完成（complete）通过 UPDATE 状态转移或回退写入日志。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..extensions import db
from ..models import EmailLog, NotificationLog
from ._common import new_id, now_utc


def has_channel_notified_today(subscription_id: str, channel: str) -> bool:
    today = date.today().isoformat()
    row = db.session.execute(
        select(NotificationLog).where(
            NotificationLog.subscription_id == subscription_id,
            NotificationLog.notification_date == today,
            NotificationLog.channel == channel,
            NotificationLog.status == "sent",
        )
    ).first()
    return row is not None


def log_notification(
    subscription_id: str, channel: str, status: str, error_message: str | None = None
) -> None:
    """幂等记录通知结果（sent 状态不可被降级）。"""
    notification_date = date.today().isoformat()
    incoming_status = str(status or "").strip().lower() or "failed"
    created_at = now_utc()
    stmt = (
        sqlite_insert(NotificationLog)
        .values(
            id=new_id(),
            subscription_id=subscription_id,
            notification_date=notification_date,
            channel=channel,
            status=incoming_status,
            error_message=error_message,
            created_at=created_at,
        )
        .on_conflict_do_update(
            index_elements=["subscription_id", "notification_date", "channel"],
            set_={
                "status": sqlite_insert(NotificationLog).excluded.status,
                "error_message": sqlite_insert(NotificationLog).excluded.error_message,
                "created_at": sqlite_insert(NotificationLog).excluded.created_at,
            },
            where=NotificationLog.status != "sent",
        )
    )
    db.session.execute(stmt)
    db.session.commit()


def log_email(to_address: str, subject: str, status: str, error_message: str | None = None) -> None:
    db.session.add(
        EmailLog(
            id=new_id(),
            to_address=to_address,
            subject=subject,
            status=status,
            error_message=error_message,
            sent_at=now_utc() if status == "sent" else None,
            created_at=now_utc(),
        )
    )
    db.session.commit()


def claim_notification(subscription_id: str, channel: str) -> str | None:
    """原子领取某订阅/渠道/当天的发送名额（单语句 UPSERT，线程安全）。"""
    sub_id = str(subscription_id or "").strip()
    channel_name = str(channel or "").strip()
    if not sub_id or not channel_name:
        return None
    today = date.today().isoformat()
    # TTL 截断线：pending 超过 6 小时视为失效，可被重新领取
    ttl_cutoff = (datetime.now(timezone.utc) - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")

    claim_id = new_id()
    stmt = (
        sqlite_insert(NotificationLog)
        .values(
            id=claim_id,
            subscription_id=sub_id,
            notification_date=today,
            channel=channel_name,
            status="pending",
            error_message=None,
            created_at=now_utc(),
        )
        .on_conflict_do_update(
            index_elements=["subscription_id", "notification_date", "channel"],
            set_={
                "id": sqlite_insert(NotificationLog).excluded.id,
                "status": "pending",
                "error_message": None,
                "created_at": sqlite_insert(NotificationLog).excluded.created_at,
            },
            # 语义（与旧实现一致）：
            # - sent / abandoned -> 终态，禁止重新领取
            # - pending 且新鲜   -> 他人在领取中，返回 None
            # - pending 超时     -> 可重新领取（TTL 截断线）
            # - failed / 其他    -> 可随时重新领取
            where=(
                ~NotificationLog.status.in_(("sent", "abandoned"))
                & (
                    (NotificationLog.status != "pending")
                    | (NotificationLog.created_at < ttl_cutoff)
                )
            ),
        )
    )
    result = db.session.execute(stmt)
    db.session.commit()
    if result.rowcount == 0:
        return None
    return claim_id


def complete_notification(
    claim_id: str | None,
    subscription_id: str,
    channel: str,
    status: str,
    error_message: str | None = None,
) -> None:
    """完成/失败/废弃一个 claim；claim 不存在时按传入参数回退记录日志。"""
    valid_statuses = {"pending", "sent", "failed", "abandoned"}
    if status not in valid_statuses or status == "pending":
        status = "failed"
    sub_id = str(subscription_id or "").strip()
    channel_name = str(channel or "").strip()
    claim = str(claim_id or "")

    if claim and not claim.startswith(("memory:", "legacy:")):
        result = db.session.execute(
            update(NotificationLog)
            .where(NotificationLog.id == claim)
            .values(status=status, error_message=error_message)
        )
        db.session.commit()
        if result.rowcount:
            return

    if sub_id and channel_name:
        log_notification(sub_id, channel_name, status, error_message)
