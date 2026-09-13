"""应用设置仓储：全局设置的读取与更新。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..extensions import db
from ..models import AppSettings
from ._common import SETTINGS_FIELDS, now_utc


def get_app_settings() -> dict:
    row = db.session.get(AppSettings, 1)
    if row is None:
        # 兜底：bootstrap 已保证单行存在，这里防御性补种
        row = AppSettings(id=1, created_at=now_utc(), updated_at=now_utc())
        db.session.add(row)
        db.session.commit()
    return row.to_dict()


def update_app_settings(updates: Mapping[str, Any]) -> dict:
    """按设置字段白名单更新；返回最新设置。"""
    allowed = {k: v for k, v in updates.items() if k in SETTINGS_FIELDS}
    row = db.session.get(AppSettings, 1)
    if row is None:
        row = AppSettings(id=1, created_at=now_utc(), updated_at=now_utc())
        db.session.add(row)
    for key, value in allowed.items():
        setattr(row, key, value)
    row.updated_at = now_utc()
    db.session.commit()
    return row.to_dict()
