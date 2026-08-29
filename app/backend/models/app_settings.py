"""全局应用设置实体（单行，id 恒为 1）。"""
from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, Float, Integer, String

from ..extensions import db


class AppSettings(db.Model):
    __tablename__ = "app_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_app_settings_singleton"),
    )

    id = Column(Integer, primary_key=True, autoincrement=False)
    dark_mode = Column(String(16), nullable=False, default="system")
    default_currency = Column(String(8), nullable=False, default="CNY")
    exchange_rate_usd = Column(Float, nullable=False, default=7.2)
    exchange_rate_hkd = Column(Float, nullable=False, default=0.92)
    notification_days = Column(Integer, nullable=False, default=7)
    do_not_disturb_start = Column(String(8), nullable=True)
    do_not_disturb_end = Column(String(8), nullable=True)
    auto_start = Column(Integer, nullable=False, default=0)
    tray_mode = Column(Integer, nullable=False, default=1)
    email_enabled = Column(Integer, nullable=False, default=0)
    smtp_host = Column(String(255), nullable=True)
    smtp_port = Column(Integer, nullable=True)
    smtp_username = Column(String(255), nullable=True)
    smtp_password = Column(String(512), nullable=True)
    smtp_from_address = Column(String(255), nullable=True)
    email_template = Column(String(32), nullable=False, default="default")
    notification_enabled = Column(Integer, nullable=False, default=1)
    pushplus_enabled = Column(Integer, nullable=False, default=0)
    pushplus_token = Column(String(512), nullable=True)
    pushplus_smtp_host = Column(String(255), nullable=True)
    pushplus_smtp_port = Column(Integer, nullable=True)
    pushplus_smtp_username = Column(String(255), nullable=True)
    pushplus_smtp_password = Column(String(512), nullable=True)
    pushplus_smtp_from_address = Column(String(255), nullable=True)
    last_check_date = Column(String(16), nullable=True)
    last_rate_update = Column(String(32), nullable=True)
    created_at = Column(String(32), nullable=False)
    updated_at = Column(String(32), nullable=False)

    # 可序列化的布尔字段
    _BOOL_FIELDS = ("auto_start", "tray_mode", "email_enabled",
                    "notification_enabled", "pushplus_enabled")

    def to_dict(self) -> dict:
        data = {column.name: getattr(self, column.name) for column in self.__table__.columns}
        for key in self._BOOL_FIELDS:
            data[key] = bool(data[key])
        return data
