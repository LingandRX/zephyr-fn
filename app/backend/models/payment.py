"""支付流水实体。"""

from __future__ import annotations

from sqlalchemy import Column, Index, Integer, String

from ..extensions import db


class Payment(db.Model):
    __tablename__ = "payments"
    __table_args__ = (
        Index("idx_payment_user_date_status", "user_id", "paid_at", "status"),
        Index("idx_payment_sub_date", "subscription_id", "paid_at"),
        Index("idx_payment_period", "period_start", "period_end"),
    )

    id = Column(String(32), primary_key=True)
    subscription_id = Column(String(32), nullable=False)
    user_id = Column(String(128), nullable=False)
    amount = Column(Integer, nullable=False)
    currency = Column(String(8), nullable=False)
    paid_at = Column(String(32), nullable=False)
    period_start = Column(String(10), nullable=False)
    period_end = Column(String(10), nullable=False)
    payment_type = Column(String(16), nullable=False)  # first/renewal/refund/adjustment
    status = Column(String(16), nullable=False, default="success")  # pending/success/failed/refunded
    external_txn_id = Column(String(64), nullable=True)
    note = Column(String(200), nullable=True)
    created_at = Column(String(32), nullable=False)

    def to_dict(self) -> dict:
        return {column.name: getattr(self, column.name) for column in self.__table__.columns}
