"""订阅实体。"""
from __future__ import annotations

from sqlalchemy import Column, Index, Integer, String

from ..extensions import db


class Subscription(db.Model):
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("idx_sub_user", "user_id"),
        Index("idx_sub_next", "next_due_date"),
    )

    id = Column(String(32), primary_key=True)
    user_id = Column(String(128), nullable=False)
    name = Column(String(200), nullable=False)
    amount = Column(Integer, nullable=False)
    currency = Column(String(8), nullable=False)
    actual_amount = Column(Integer, nullable=True)
    category_id = Column(String(32), nullable=True)
    notes = Column(String(120), nullable=True)
    period_type = Column(String(16), nullable=False)
    custom_period_value = Column(Integer, nullable=True)
    custom_period_unit = Column(String(8), nullable=True)
    auto_renew = Column(Integer, nullable=False, default=1)
    sharing_role = Column(String(64), nullable=True)
    sharing_count = Column(Integer, nullable=True)
    start_date = Column(String(10), nullable=False)
    first_payment_date = Column(String(10), nullable=True)
    next_due_date = Column(String(10), nullable=True)
    lifecycle = Column(String(16), nullable=False, default="active")
    renewal_policy = Column(String(16), nullable=False, default="auto")
    billing_status = Column(String(16), nullable=False, default="normal")
    grace_period_ends_at = Column(String(10), nullable=True)
    sync_version = Column(Integer, nullable=False, default=1)
    created_at = Column(String(32), nullable=False)
    updated_at = Column(String(32), nullable=False)

    def to_dict(self) -> dict:
        data = {column.name: getattr(self, column.name) for column in self.__table__.columns}
        data["auto_renew"] = bool(data["auto_renew"])
        return data
