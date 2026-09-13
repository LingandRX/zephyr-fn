"""订阅仓储：订阅实体的 CRUD、软删除、恢复、续费、去重、备份等操作。"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import Subscription
from ._common import SUBSCRIPTION_COLUMNS, SUBSCRIPTION_FIELDS, new_id, now_utc


def get_all_subscriptions(user_id: str, include_deleted: bool = False) -> list[dict]:
    stmt = select(Subscription).where(Subscription.user_id == user_id)
    if not include_deleted:
        stmt = stmt.where(Subscription.deleted_at.is_(None))
    rows = db.session.execute(
        stmt.order_by(Subscription.next_due_date.asc(), Subscription.name.asc())
    ).scalars()
    return [row.to_dict() for row in rows]


def get_subscription_by_id(
    sub_id: str, user_id: str, include_deleted: bool = False
) -> dict | None:
    row = db.session.get(Subscription, sub_id)
    if row is None or row.user_id != user_id:
        return None
    if not include_deleted and row.deleted_at is not None:
        return None
    return row.to_dict()


def insert_subscription(normalized: Mapping[str, Any]) -> dict:
    """插入订阅行（调用方需传入已归一化的全列字典）。"""
    row = Subscription(**{k: normalized.get(k) for k in SUBSCRIPTION_COLUMNS})
    db.session.add(row)
    db.session.commit()
    return row.to_dict()


def update_subscription_fields(
    sub_id: str, user_id: str, updates: Mapping[str, Any]
) -> dict | None:
    """按字段白名单更新订阅；返回更新后的行，不存在返回 None。"""
    row = db.session.get(Subscription, sub_id)
    if row is None or row.user_id != user_id or row.deleted_at is not None:
        return None
    allowed = {k: v for k, v in updates.items() if k in SUBSCRIPTION_FIELDS}
    if not allowed:
        return row.to_dict()
    for k, v in allowed.items():
        setattr(row, k, v)
    row.updated_at = now_utc()
    db.session.commit()
    return row.to_dict()


def delete_subscription(sub_id: str, user_id: str, hard: bool = False) -> bool:
    """删除订阅。默认软删除（置 deleted_at）；hard=True 时物理删除。"""
    row = db.session.execute(
        select(Subscription).where(
            Subscription.id == sub_id,
            Subscription.user_id == user_id,
            Subscription.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    if hard:
        db.session.delete(row)
    else:
        row.deleted_at = now_utc()
        row.updated_at = now_utc()
    db.session.commit()
    return True


def restore_subscription(sub_id: str, user_id: str) -> dict | None:
    """恢复已软删除的订阅。"""
    row = db.session.execute(
        select(Subscription).where(
            Subscription.id == sub_id,
            Subscription.user_id == user_id,
            Subscription.deleted_at.is_not(None),
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    row.deleted_at = None
    row.updated_at = now_utc()
    db.session.commit()
    return row.to_dict()


def renew_subscription(sub_id: str, user_id: str, next_due: str) -> dict | None:
    """推进续费：置 next_due_date 并复位生命周期/账单状态。"""
    row = db.session.get(Subscription, sub_id)
    if row is None or row.user_id != user_id or row.deleted_at is not None:
        return None
    row.next_due_date = next_due
    row.current_period_end = next_due
    row.lifecycle = "active"
    row.billing_status = "normal"
    row.renewal_confirmed = 0
    row.updated_at = now_utc()
    db.session.commit()
    return row.to_dict()


def get_all_subscriptions_raw(
    user_id: str | None = None, include_deleted: bool = False
) -> list[dict]:
    """读取原始订阅；传入 user_id 时只返回该用户数据。默认过滤软删除。"""
    stmt = select(Subscription).order_by(Subscription.id)
    if user_id is not None:
        stmt = stmt.where(Subscription.user_id == user_id)
    if not include_deleted:
        stmt = stmt.where(Subscription.deleted_at.is_(None))
    return [row.to_dict() for row in db.session.execute(stmt).scalars()]


def get_subscription_dedup_keys(user_id: str | None = None) -> set:
    """去重键：名称|金额|周期类型（仅未删除项）。"""
    stmt = select(Subscription.name, Subscription.amount, Subscription.period_type).where(
        Subscription.deleted_at.is_(None)
    )
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


def get_subscriptions_paginated(
    user_id: str,
    page: int = 1,
    per_page: int = 20,
    lifecycle: str | None = None,
    category_id: str | None = None,
) -> tuple[list[dict], int]:
    """分页查询订阅列表，返回 (items, total_count)。

    Parameters
    ----------
    user_id : 用户 ID
    page : 页码（从 1 开始）
    per_page : 每页数量（1-100）
    lifecycle : 生命周期过滤（可选）
    category_id : 分类 ID 过滤（可选）
    """
    stmt = select(Subscription).where(
        Subscription.user_id == user_id,
        Subscription.deleted_at.is_(None),
    )
    if lifecycle:
        stmt = stmt.where(Subscription.lifecycle == lifecycle)
    if category_id:
        stmt = stmt.where(Subscription.category_id == category_id)

    # 总数查询
    from sqlalchemy import func
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.session.execute(count_stmt).scalar_one()

    # 分页查询
    stmt = stmt.order_by(Subscription.next_due_date.asc(), Subscription.name.asc())
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)
    items = [row.to_dict() for row in db.session.execute(stmt).scalars()]

    return items, total
