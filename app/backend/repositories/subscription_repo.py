"""订阅仓储：订阅实体的 CRUD、软删除、恢复、续费、去重等操作。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select

from ..extensions import db
from ..models import Subscription
from ._common import SUBSCRIPTION_COLUMNS, SUBSCRIPTION_FIELDS, now_utc


def list_ordering() -> tuple:
    """订阅列表统一排序键。

    下次扣费日升序（最早的排最前）；一次性订阅的 ``next_due_date`` 为 NULL，
    用 ``is_(None)`` 显式归到末位，避免 SQLite（NULL 在前）与 PostgreSQL（NULL 在后）
    的方言差异；同一扣费日再按名称升序。
    """
    return (
        Subscription.next_due_date.is_(None),
        Subscription.next_due_date.asc(),
        Subscription.name.asc(),
    )


def get_all_subscriptions(user_id: str) -> list[dict]:
    stmt = (
        select(Subscription)
        .where(Subscription.user_id == user_id, Subscription.deleted_at.is_(None))
        .order_by(*list_ordering())
    )
    return [row.to_dict() for row in db.session.execute(stmt).scalars()]


def get_subscription_by_id(sub_id: str, user_id: str) -> dict | None:
    row = db.session.get(Subscription, sub_id)
    if row is None or row.user_id != user_id or row.deleted_at is not None:
        return None
    return row.to_dict()


def insert_subscription(normalized: Mapping[str, Any]) -> dict:
    """插入订阅行（调用方需传入已归一化的全列字典）。"""
    row = Subscription(**{k: normalized.get(k) for k in SUBSCRIPTION_COLUMNS})
    db.session.add(row)
    db.session.flush()
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
    db.session.flush()
    return row.to_dict()


def delete_subscription(sub_id: str, user_id: str) -> bool:
    """软删除订阅（置 deleted_at）。"""
    row = db.session.execute(
        select(Subscription).where(
            Subscription.id == sub_id,
            Subscription.user_id == user_id,
            Subscription.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    row.deleted_at = now_utc()
    row.updated_at = now_utc()
    db.session.flush()
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
    db.session.flush()
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
    db.session.flush()
    return row.to_dict()


def get_all_subscriptions_raw(user_id: str | None = None) -> list[dict]:
    """读取原始订阅；传入 user_id 时只返回该用户数据（过滤软删除）。"""
    stmt = select(Subscription).where(Subscription.deleted_at.is_(None))
    if user_id is not None:
        stmt = stmt.where(Subscription.user_id == user_id)
    return [row.to_dict() for row in db.session.execute(stmt.order_by(Subscription.id)).scalars()]


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
    stmt = stmt.order_by(*list_ordering())
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)
    items = [row.to_dict() for row in db.session.execute(stmt).scalars()]

    return items, total
