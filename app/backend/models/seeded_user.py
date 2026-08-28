"""默认分类补种标记实体（记录已播种过默认分类的用户）。"""
from __future__ import annotations

from sqlalchemy import Column, String

from ..extensions import db


class SeededUser(db.Model):
    __tablename__ = "seeded_users"

    user_id = Column(String(128), primary_key=True)
    seeded_at = Column(String(32), nullable=False)
