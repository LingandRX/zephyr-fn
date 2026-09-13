"""支付流水仓储：支付记录的查询、插入与自动汇率补齐。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ..extensions import db
from ..models import Payment
from ._common import new_id, now_utc


def get_all_payments(user_id: str) -> list[dict]:
    """获取用户的所有支付流水。"""
    rows = db.session.execute(
        select(Payment)
        .where(Payment.user_id == user_id)
        .order_by(Payment.paid_at.desc())
    ).scalars()
    return [row.to_dict() for row in rows]


def get_payments_by_subscription(subscription_id: str, user_id: str | None = None) -> list[dict]:
    """获取订阅的所有支付流水（可按用户隔离）。"""
    stmt = select(Payment).where(Payment.subscription_id == subscription_id)
    if user_id is not None:
        stmt = stmt.where(Payment.user_id == user_id)
    rows = db.session.execute(
        stmt.order_by(Payment.paid_at.desc())
    ).scalars()
    return [row.to_dict() for row in rows]


def get_payments_by_date_range(
    user_id: str,
    start_date: str,
    end_date: str,
    status: str = "success"
) -> list[dict]:
    """获取指定日期范围内的支付流水（闭区间：start_date <= paid_at <= end_date）。"""
    rows = db.session.execute(
        select(Payment)
        .where(
            Payment.user_id == user_id,
            Payment.status == status,
            Payment.paid_at >= start_date,
            Payment.paid_at <= end_date
        )
        .order_by(Payment.paid_at.desc())
    ).scalars()
    return [row.to_dict() for row in rows]


def _get_settings_for_exchange() -> dict:
    """内部获取设置（延迟导入避免循环引用）。"""
    from .settings_repo import get_app_settings

    return get_app_settings()


def insert_payment(payment_data: dict) -> dict:
    """插入支付流水。若未显式指定汇率或本位币金额，则根据当前设置快照自动补齐。"""
    data = dict(payment_data)
    amount = int(data.get("amount") or 0)
    currency = str(data.get("currency") or "CNY").upper()

    if data.get("exchange_rate") is None:
        settings = _get_settings_for_exchange()
        if currency == "USD":
            data["exchange_rate"] = float(settings.get("exchange_rate_usd") or 7.2)
        elif currency == "HKD":
            data["exchange_rate"] = float(settings.get("exchange_rate_hkd") or 0.92)
        else:
            data["exchange_rate"] = 1.0
    else:
        data["exchange_rate"] = float(data["exchange_rate"])

    if data.get("amount_cny") is None:
        rate = data["exchange_rate"]
        data["amount_cny"] = round(amount * rate) if currency != "CNY" else amount
    else:
        data["amount_cny"] = int(data["amount_cny"])

    row = Payment(**data)
    db.session.add(row)
    db.session.commit()
    return row.to_dict()


def create_payment_for_subscription(
    subscription_id: str,
    user_id: str,
    amount: int,
    currency: str,
    paid_at: str,
    period_start: str,
    period_end: str,
    payment_type: str,
    note: str | None = None,
    exchange_rate: float | None = None,
    amount_cny: int | None = None,
) -> dict:
    """为订阅创建支付流水。"""
    payment_data = {
        "id": new_id(),
        "subscription_id": subscription_id,
        "user_id": user_id,
        "amount": amount,
        "currency": currency,
        "exchange_rate": exchange_rate,
        "amount_cny": amount_cny,
        "paid_at": paid_at,
        "period_start": period_start,
        "period_end": period_end,
        "payment_type": payment_type,
        "status": "success",
        "note": note,
        "created_at": now_utc(),
    }
    return insert_payment(payment_data)
