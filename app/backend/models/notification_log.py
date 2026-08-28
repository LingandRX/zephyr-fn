"""通知日志实体（到期提醒发放记录）。"""
from __future__ import annotations

from sqlalchemy import Column, Index, Integer, String

from ..extensions import db


class NotificationLog(db.Model):
    __tablename__ = "notification_logs"
    __table_args__ = (
        Index(
            "idx_notification_logs_identity",
            "subscription_id", "notification_date", "channel",
            unique=True,
        ),
        Index("idx_notif_sub_date", "subscription_id", "notification_date"),
    )

    id = Column(String(40), primary_key=True)
    subscription_id = Column(String(32), nullable=False)
    notification_date = Column(String(10), nullable=False)
    channel = Column(String(16), nullable=False)
    status = Column(String(16), nullable=False, default="sent")
    error_message = Column(String(512), nullable=True)
    created_at = Column(String(32), nullable=False)
