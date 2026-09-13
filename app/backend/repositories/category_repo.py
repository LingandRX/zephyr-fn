"""分类仓储：分类实体的 CRUD、去重、批量插入等操作。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select, update

from ..extensions import db
from ..models import Category, Subscription
from ._common import new_id, now_utc, _to_int


def get_all_categories(user_id: str) -> list[dict]:
    rows = db.session.execute(
        select(Category)
        .where(Category.user_id == user_id)
        .order_by(Category.sort_order.asc(), Category.name.asc())
    ).scalars()
    return [row.to_dict() for row in rows]


def get_all_categories_raw(user_id: str | None = None) -> list[dict]:
    stmt = select(Category).order_by(Category.id)
    if user_id is not None:
        stmt = stmt.where(Category.user_id == user_id)
    return [row.to_dict() for row in db.session.execute(stmt).scalars()]


def get_category_by_id(cat_id: str, user_id: str) -> dict | None:
    row = db.session.execute(
        select(Category).where(Category.id == cat_id, Category.user_id == user_id)
    ).scalar_one_or_none()
    return row.to_dict() if row else None


def get_category_count(user_id: str) -> int:
    from sqlalchemy import func

    return db.session.execute(
        select(func.count()).select_from(Category).where(Category.user_id == user_id)
    ).scalar_one()


def insert_category(user_id: str, name: str, icon: str | None, sort_order: int) -> dict:
    from sqlalchemy.exc import IntegrityError

    row = Category(id=new_id(), user_id=user_id, name=name, icon=icon, sort_order=sort_order)
    db.session.add(row)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        if "idx_cat_user_name" in str(exc) or "UNIQUE" in str(exc):
            from ..domain.exceptions import ConflictError

            raise ConflictError("分类已存在") from exc
        raise
    return row.to_dict()


def update_category(cat_id: str, user_id: str, updates: Mapping[str, Any]) -> dict | None:
    from sqlalchemy.exc import IntegrityError

    row = db.session.execute(
        select(Category).where(Category.id == cat_id, Category.user_id == user_id)
    ).scalar_one_or_none()
    if row is None:
        return None
    for key, value in updates.items():
        setattr(row, key, value)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        if "idx_cat_user_name" in str(exc) or "UNIQUE" in str(exc):
            from ..domain.exceptions import ConflictError

            raise ConflictError("分类已存在") from exc
        raise
    return row.to_dict()


def insert_category_raw(cat: Mapping[str, Any], user_id: str | None = None) -> bool:
    """安全插入外部分类；id 冲突时忽略，不覆盖任何用户的分类。"""
    if not isinstance(cat, Mapping):
        raise ValueError("分类数据必须是对象")
    cat_id = str(cat.get("id") or "").strip()
    if not cat_id:
        raise ValueError("分类 id 不能为空")
    name = str(cat.get("name") or "未分类").strip() or "未分类"
    owner = str(user_id if user_id is not None else cat.get("user_id", "local") or "local")
    if db.session.get(Category, cat_id) is not None:
        return False
    db.session.add(
        Category(
            id=cat_id,
            user_id=owner,
            name=name,
            icon=cat.get("icon"),
            sort_order=_to_int(cat.get("sort_order"), 0),
        )
    )
    db.session.commit()
    return True


def delete_category(cat_id: str, user_id: str) -> bool:
    """删除分类，并把该用户的订阅从该分类解绑。"""
    db.session.execute(
        update(Subscription)
        .where(Subscription.category_id == cat_id, Subscription.user_id == user_id)
        .values(category_id=None, updated_at=now_utc())
    )
    row = db.session.execute(
        select(Category).where(Category.id == cat_id, Category.user_id == user_id)
    ).scalar_one_or_none()
    if row is None:
        db.session.commit()
        return False
    db.session.delete(row)
    db.session.commit()
    return True
