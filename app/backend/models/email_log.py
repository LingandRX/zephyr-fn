"""邮件发送日志实体。"""
from __future__ import annotations

from sqlalchemy import Column, Integer, String

from ..extensions import db


class EmailLog(db.Model):
    __tablename__ = "email_logs"

    id = Column(String(32), primary_key=True)
    to_address = Column(String(255), nullable=False)
    subject = Column(String(512), nullable=False)
    status = Column(String(16), nullable=False, default="pending")
    error_message = Column(String(512), nullable=True)
    sent_at = Column(String(32), nullable=True)
    created_at = Column(String(32), nullable=False)
