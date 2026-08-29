"""数据持久化仓储层（SQLAlchemy 实现）。

旧版 storage/db.py 的职责按四层架构拆解：
- 查询与写入   → 本模块（仓储函数，会话自动提交）
- 校验与归一化 → schemas/ 与 services/（业务层）
- 旧库就地升级 → storage/bootstrap.py

会话生命周期由 Flask-SQLAlchemy 绑定应用/请求上下文管理；
后台线程（定时任务）通过 ``with app.app_context()`` 显式持有上下文。
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import select, text, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import (
    AppSettings,
    Category,
    EmailLog,
    NotificationLog,
    SeededUser,
    Subscription,
)

# 订阅全量列（写入顺序固定，供 raw 导入/替换使用）
SUBSCRIPTION_COLUMNS = (
    "id", "user_id", "name", "amount", "currency", "actual_amount",
    "category_id", "notes", "period_type", "custom_period_value",
    "custom_period_unit", "auto_renew", "sharing_role", "sharing_count",
    "start_date", "first_payment_date", "next_due_date", "lifecycle",
    "renewal_policy", "billing_status", "grace_period_ends_at",
    "sync_version", "created_at", "updated_at",
)

# 可更新的订阅字段白名单
SUBSCRIPTION_FIELDS = (
    "name", "amount", "currency", "actual_amount", "category_id", "notes",
    "period_type", "custom_period_value", "custom_period_unit", "auto_renew",
    "sharing_role", "sharing_count", "start_date", "first_payment_date",
    "next_due_date", "lifecycle", "renewal_policy", "billing_status",
    "grace_period_ends_at",
)

# 设置字段白名单
SETTINGS_FIELDS = (
    "dark_mode", "default_currency", "exchange_rate_usd", "exchange_rate_hkd",
    "notification_days", "do_not_disturb_start", "do_not_disturb_end",
    "auto_start", "tray_mode", "email_enabled", "smtp_host", "smtp_port",
    "smtp_username", "smtp_password", "smtp_from_address", "email_template",
    "notification_enabled", "pushplus_enabled", "pushplus_token",
    "pushplus_smtp_host", "pushplus_smtp_port", "pushplus_smtp_username",
    "pushplus_smtp_password", "pushplus_smtp_from_address",
    "last_check_date", "last_rate_update",
)

_SECRET_SETTING_FIELDS = frozenset({
    "smtp_password", "pushplus_token", "pushplus_smtp_password",
})
_SECRET_MASK_EXACT = frozenset({
    "***", "******", "********", "**********", "************",
    "••••", "••••••", "••••••••", "[redacted]", "[已配置]",
    "已配置", "configured",
})


# --------------------------------------------------------------------------- #
# 通用工具
# --------------------------------------------------------------------------- #

def new_id() -> str:
    return uuid.uuid4().hex


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def is_secret_placeholder(value: Any) -> bool:
    """判断设置请求中的值是否表示“保持原密钥”。"""
    if value is None:
        return True
    text_value = str(value).strip()
    if not text_value:
        return True
    lowered = text_value.lower()
    if lowered in _SECRET_MASK_EXACT:
        return True
    if "已配置" in text_value or lowered in {"redacted", "masked"}:
        return True
    mask_chars = {"*", "•", "·", "●"}
    return len(text_value) >= 3 and all(char in mask_chars for char in text_value)


# --------------------------------------------------------------------------- #
# 订阅仓储
# --------------------------------------------------------------------------- #

def get_all_subscriptions(user_id: str) -> list[dict]:
    rows = db.session.execute(
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .order_by(Subscription.next_due_date.asc(), Subscription.name.asc())
    ).scalars()
    return [row.to_dict() for row in rows]


def get_subscription_by_id(sub_id: str, user_id: str) -> dict | None:
    row = db.session.get(Subscription, sub_id)
    if row is None or row.user_id != user_id:
        return None
    return row.to_dict()


def insert_subscription(normalized: Mapping[str, Any]) -> dict:
    """插入订阅行（调用方需传入已归一化的全列字典）。"""
    row = Subscription(**{k: normalized[k] for k in SUBSCRIPTION_COLUMNS})
    db.session.add(row)
    db.session.commit()
    return row.to_dict()


def update_subscription_fields(
    sub_id: str, user_id: str, updates: Mapping[str, Any]
) -> dict | None:
    """按字段白名单更新订阅；返回更新后的行，不存在返回 None。"""
    row = db.session.get(Subscription, sub_id)
    if row is None or row.user_id != user_id:
        return None
    allowed = {k: v for k, v in updates.items() if k in SUBSCRIPTION_FIELDS}
    if not allowed:
        return row.to_dict()
    for k, v in allowed.items():
        setattr(row, k, v)
    row.updated_at = now_utc()
    db.session.commit()
    return row.to_dict()


def delete_subscription(sub_id: str, user_id: str) -> bool:
    row = db.session.execute(
        select(Subscription).where(Subscription.id == sub_id,
                                   Subscription.user_id == user_id)
    ).scalar_one_or_none()
    if row is None:
        return False
    db.session.delete(row)
    db.session.commit()
    return True


def renew_subscription(sub_id: str, user_id: str, next_due: str) -> dict | None:
    """推进续费：置 next_due_date 并复位生命周期/账单状态。"""
    row = db.session.get(Subscription, sub_id)
    if row is None or row.user_id != user_id:
        return None
    row.next_due_date = next_due
    row.lifecycle = "active"
    row.billing_status = "normal"
    row.updated_at = now_utc()
    db.session.commit()
    return row.to_dict()


def get_all_subscriptions_raw(user_id: str | None = None) -> list[dict]:
    """读取原始订阅；传入 user_id 时只返回该用户数据。"""
    stmt = select(Subscription).order_by(Subscription.id)
    if user_id is not None:
        stmt = stmt.where(Subscription.user_id == user_id)
    return [row.to_dict() for row in db.session.execute(stmt).scalars()]


def get_subscription_dedup_keys(user_id: str | None = None) -> set:
    """去重键：名称|金额|周期类型。"""
    stmt = select(Subscription.name, Subscription.amount, Subscription.period_type)
    if user_id is not None:
        stmt = stmt.where(Subscription.user_id == user_id)
    return {
        f"{name}|{amount}|{period_type}".lower()
        for name, amount, period_type in db.session.execute(stmt)
    }


def insert_subscription_raw(normalized: Mapping[str, Any]) -> dict:
    """安全插入外部订阅行，id 冲突时换新 id，绝不覆盖已有行。"""
    candidate = {k: normalized[k] for k in SUBSCRIPTION_COLUMNS}
    while True:
        try:
            row = Subscription(**candidate)
            db.session.add(row)
            db.session.commit()
            return row.to_dict()
        except IntegrityError:
            db.session.rollback()
            exists = db.session.get(Subscription, candidate["id"]) is not None
            if not exists:
                raise
            candidate["id"] = new_id()


def replace_subscription_raw(normalized: Mapping[str, Any]) -> bool:
    """按 owner 安全替换订阅行，不允许跨用户覆盖。"""
    candidate = {k: normalized[k] for k in SUBSCRIPTION_COLUMNS}
    sub_id = candidate["id"]
    owner = candidate["user_id"]
    existing = db.session.get(Subscription, sub_id)
    if existing is not None and existing.user_id != owner:
        return False
    if existing is not None:
        for column in SUBSCRIPTION_COLUMNS:
            if column not in ("id", "user_id"):
                setattr(existing, column, candidate[column])
    else:
        db.session.add(Subscription(**candidate))
    db.session.commit()
    return True


def export_db_copy(target_path: Path) -> None:
    """在线备份数据库文件副本（sqlite3 backup API，锁安全）。"""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    source = db.engine.raw_connection()
    dest = sqlite3.connect(str(target_path))
    try:
        source.backup(dest)
    finally:
        dest.close()
        source.close()


# --------------------------------------------------------------------------- #
# 分类仓储
# --------------------------------------------------------------------------- #

def get_all_categories(user_id: str) -> list[dict]:
    rows = db.session.execute(
        select(Category)
        .where(Category.user_id == user_id)
        .order_by(Category.sort_order.asc(), Category.name.asc())
    ).scalars()
    return [row.to_dict() for row in rows]


def get_all_categories_raw(user_id: str | None = None) -> list[dict]:
    stmt = select(Category).order_by(Category.id)
    if user_id is not None:
        stmt = stmt.where(Category.user_id == user_id)
    return [row.to_dict() for row in db.session.execute(stmt).scalars()]


def get_category_by_id(cat_id: str, user_id: str) -> dict | None:
    row = db.session.execute(
        select(Category).where(Category.id == cat_id, Category.user_id == user_id)
    ).scalar_one_or_none()
    return row.to_dict() if row else None


def get_category_count(user_id: str) -> int:
    from sqlalchemy import func
    return db.session.execute(
        select(func.count()).select_from(Category).where(Category.user_id == user_id)
    ).scalar_one()


def insert_category(user_id: str, name: str, icon: str | None,
                    sort_order: int) -> dict:
    row = Category(id=new_id(), user_id=user_id, name=name, icon=icon,
                   sort_order=sort_order)
    db.session.add(row)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        if "idx_cat_user_name" in str(exc) or "UNIQUE" in str(exc):
            from ..core.exceptions import ConflictError
            raise ConflictError("分类已存在") from exc
        raise
    return row.to_dict()


def update_category(cat_id: str, user_id: str, updates: Mapping[str, Any]) -> dict | None:
    row = db.session.execute(
        select(Category).where(Category.id == cat_id, Category.user_id == user_id)
    ).scalar_one_or_none()
    if row is None:
        return None
    for key, value in updates.items():
        setattr(row, key, value)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        if "idx_cat_user_name" in str(exc) or "UNIQUE" in str(exc):
            from ..core.exceptions import ConflictError
            raise ConflictError("分类已存在") from exc
        raise
    return row.to_dict()


def insert_category_raw(cat: Mapping[str, Any], user_id: str | None = None) -> bool:
    """安全插入外部分类；id 冲突时忽略，不覆盖任何用户的分类。"""
    if not isinstance(cat, Mapping):
        raise ValueError("分类数据必须是对象")
    cat_id = str(cat.get("id") or "").strip()
    if not cat_id:
        raise ValueError("分类 id 不能为空")
    name = str(cat.get("name") or "未分类").strip() or "未分类"
    owner = str(user_id if user_id is not None else cat.get("user_id", "local") or "local")
    if db.session.get(Category, cat_id) is not None:
        return False
    db.session.add(Category(id=cat_id, user_id=owner, name=name,
                            icon=cat.get("icon"),
                            sort_order=_to_int(cat.get("sort_order"), 0)))
    db.session.commit()
    return True


def delete_category(cat_id: str, user_id: str) -> bool:
    """删除分类，并把该用户的订阅从该分类解绑。"""
    db.session.execute(
        update(Subscription)
        .where(Subscription.category_id == cat_id, Subscription.user_id == user_id)
        .values(category_id=None, updated_at=now_utc())
    )
    row = db.session.execute(
        select(Category).where(Category.id == cat_id, Category.user_id == user_id)
    ).scalar_one_or_none()
    if row is None:
        db.session.commit()
        return False
    db.session.delete(row)
    db.session.commit()
    return True


# --------------------------------------------------------------------------- #
# 设置仓储
# --------------------------------------------------------------------------- #

def get_app_settings() -> dict:
    row = db.session.get(AppSettings, 1)
    if row is None:
        # 兜底：bootstrap 已保证单行存在，这里防御性补种
        row = AppSettings(id=1, created_at=now_utc(), updated_at=now_utc())
        db.session.add(row)
        db.session.commit()
    return row.to_dict()


def update_app_settings(updates: Mapping[str, Any]) -> dict:
    """按设置字段白名单更新；返回最新设置。"""
    allowed = {k: v for k, v in updates.items() if k in SETTINGS_FIELDS}
    row = db.session.get(AppSettings, 1)
    if row is None:
        row = AppSettings(id=1, created_at=now_utc(), updated_at=now_utc())
        db.session.add(row)
    for key, value in allowed.items():
        setattr(row, key, value)
    row.updated_at = now_utc()
    db.session.commit()
    return row.to_dict()


# --------------------------------------------------------------------------- #
# 通知 / 邮件日志仓储
# --------------------------------------------------------------------------- #

def has_channel_notified_today(subscription_id: str, channel: str) -> bool:
    from datetime import date
    today = date.today().isoformat()
    row = db.session.execute(
        select(NotificationLog)
        .where(NotificationLog.subscription_id == subscription_id,
               NotificationLog.notification_date == today,
               NotificationLog.channel == channel,
               NotificationLog.status == "sent")
    ).first()
    return row is not None


def log_notification(subscription_id: str, channel: str, status: str,
                     error_message: str | None = None) -> None:
    """幂等记录通知结果（sent 状态不可被降级）。"""
    from datetime import date
    notification_date = date.today().isoformat()
    incoming_status = str(status or "").strip().lower() or "failed"
    created_at = now_utc()
    stmt = sqlite_insert(NotificationLog).values(
        id=new_id(), subscription_id=subscription_id,
        notification_date=notification_date, channel=channel,
        status=incoming_status, error_message=error_message,
        created_at=created_at,
    ).on_conflict_do_update(
        index_elements=["subscription_id", "notification_date", "channel"],
        set_={
            "status": sqlite_insert(NotificationLog).excluded.status,
            "error_message": sqlite_insert(NotificationLog).excluded.error_message,
            "created_at": sqlite_insert(NotificationLog).excluded.created_at,
        },
        where=NotificationLog.status != "sent",
    )
    db.session.execute(stmt)
    db.session.commit()


def log_email(to_address: str, subject: str, status: str,
              error_message: str | None = None) -> None:
    db.session.add(EmailLog(
        id=new_id(), to_address=to_address, subject=subject, status=status,
        error_message=error_message,
        sent_at=now_utc() if status == "sent" else None,
        created_at=now_utc(),
    ))
    db.session.commit()


def claim_notification(subscription_id: str, channel: str) -> str | None:
    """原子领取某订阅/渠道/当天的发送名额（单语句 UPSERT，线程安全）。"""
    from datetime import date, timedelta
    sub_id = str(subscription_id or "").strip()
    channel_name = str(channel or "").strip()
    if not sub_id or not channel_name:
        return None
    today = date.today().isoformat()
    # TTL 截断线：pending 超过 6 小时视为失效，可被重新领取
    ttl_cutoff = (datetime.now(timezone.utc) - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")

    claim_id = new_id()
    stmt = sqlite_insert(NotificationLog).values(
        id=claim_id, subscription_id=sub_id, notification_date=today,
        channel=channel_name, status="pending", error_message=None,
        created_at=now_utc(),
    ).on_conflict_do_update(
        index_elements=["subscription_id", "notification_date", "channel"],
        set_={
            "id": sqlite_insert(NotificationLog).excluded.id,
            "status": "pending",
            "error_message": None,
            "created_at": sqlite_insert(NotificationLog).excluded.created_at,
        },
        # 语义（与旧实现一致）：
        # - sent           -> 终态，禁止重新领取
        # - pending 且新鲜 -> 他人在领取中，返回 None
        # - pending 超时   -> 可重新领取（TTL 截断线）
        # - failed/其他    -> 可随时重新领取
        where=(
            (NotificationLog.status != "sent")
            & ((NotificationLog.status != "pending")
               | (NotificationLog.created_at < ttl_cutoff))
        ),
    )
    result = db.session.execute(stmt)
    db.session.commit()
    if result.rowcount == 0:
        return None
    return claim_id


def complete_notification(claim_id: str | None, subscription_id: str, channel: str,
                          status: str, error_message: str | None = None) -> None:
    """完成/失败一个 claim；claim 不存在时按传入参数回退记录日志。"""
    valid_statuses = {"pending", "sent", "failed"}
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


# --------------------------------------------------------------------------- #
# 默认分类补种仓储
# --------------------------------------------------------------------------- #

def is_user_seeded(user_id: str) -> bool:
    return db.session.get(SeededUser, user_id) is not None


def mark_user_seeded(user_id: str) -> None:
    db.session.add(SeededUser(user_id=user_id, seeded_at=now_utc()))
    db.session.commit()
