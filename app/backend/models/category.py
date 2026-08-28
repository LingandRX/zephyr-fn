"""订阅分类实体。"""
from __future__ import annotations

from sqlalchemy import Column, Index, Integer, String, text

from ..extensions import db


class Category(db.Model):
    __tablename__ = "categories"
    __table_args__ = (
        # 与旧库 idx_cat_user_name 一致：同名分类（大小写不敏感）全局唯一
        Index("idx_cat_user_name", "user_id", text("name COLLATE NOCASE"), unique=True),
        Index("idx_cat_user_sort", "user_id", "sort_order"),
    )

    id = Column(String(32), primary_key=True)
    user_id = Column(String(128), nullable=False)
    name = Column(String(20), nullable=False)
    icon = Column(String(8), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)

    def to_dict(self) -> dict:
        return {column.name: getattr(self, column.name) for column in self.__table__.columns}
