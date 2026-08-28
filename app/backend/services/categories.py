"""分类业务服务：名称去重/上限校验 → 仓储编排；默认分类补种。"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..core.exceptions import ConflictError, ValidationError
from ..extensions import db
from ..schemas.category import (
    MAX_CATEGORIES_PER_USER,
    normalize_category_name,
    normalize_icon,
    normalize_sort_order,
)
from ..storage import repositories
from ..storage.bootstrap import DEFAULT_CATEGORY_TEMPLATES

# 进程内已播种用户缓存（按数据库文件隔离），避免每个 API 请求都查询 seeded_users。
_seeded_cache: set[tuple[str, str]] = set()


def _db_key() -> str:
    return str(db.engine.url.database or "")


def ensure_default_categories_for_user(user_id: str) -> bool:
    """新用户首次访问时补种默认分类（幂等）。"""
    target = str(user_id or "").strip()
    if not target:
        return False
    key = (_db_key(), target)
    if key in _seeded_cache:
        return False
    if repositories.is_user_seeded(target):
        _seeded_cache.add(key)
        return False
    for name, icon, sort_order in DEFAULT_CATEGORY_TEMPLATES:
        try:
            repositories.insert_category(target, name, icon, sort_order)
        except ValueError:
            # 并发/数据异常时跳过重复分类，不阻塞补种
            continue
    repositories.mark_user_seeded(target)
    _seeded_cache.add(key)
    return True


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #

def list_categories(user_id: str) -> list[dict]:
    return repositories.get_all_categories(user_id)


def create_category(user_id: str, data: Mapping[str, Any]) -> dict:
    name = normalize_category_name(data.get("name"))
    icon = normalize_icon(data.get("icon"))
    sort_order = normalize_sort_order(data.get("sort_order"))
    _ensure_unique_name(user_id, name, exclude_id=None)
    if repositories.get_category_count(user_id) >= MAX_CATEGORIES_PER_USER:
        raise ConflictError(f"分类数量已达上限({MAX_CATEGORIES_PER_USER})")
    return repositories.insert_category(user_id, name, icon, sort_order)


def update_category(cat_id: str, user_id: str, data: Mapping[str, Any]) -> dict | None:
    if not isinstance(data, Mapping):
        raise ValidationError("请求数据必须是对象")
    updates: dict[str, Any] = {}
    if "name" in data:
        name = normalize_category_name(data.get("name"))
        _ensure_unique_name(user_id, name, exclude_id=cat_id)
        updates["name"] = name
    if "icon" in data:
        updates["icon"] = normalize_icon(data.get("icon"))
    if "sort_order" in data:
        updates["sort_order"] = normalize_sort_order(data.get("sort_order"))
    if not updates:
        return repositories.get_category_by_id(cat_id, user_id)
    return repositories.update_category(cat_id, user_id, updates)


def delete_category(cat_id: str, user_id: str) -> bool:
    return repositories.delete_category(cat_id, user_id)


def _ensure_unique_name(user_id: str, name: str, exclude_id: str | None = None) -> None:
    """同名分类（大小写不敏感）唯一性检查。"""
    normalized = name
    for cat in repositories.get_all_categories_raw(user_id):
        if exclude_id and cat["id"] == exclude_id:
            continue
        if cat["name"].lower() == normalized.lower():
            raise ConflictError("分类已存在")


# --------------------------------------------------------------------------- #
# 备份/导入导出辅助
# --------------------------------------------------------------------------- #

def insert_category_raw(cat: Mapping[str, Any], user_id: str | None = None) -> bool:
    return repositories.insert_category_raw(cat, user_id)
