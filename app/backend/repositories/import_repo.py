"""批量导入仓储。

提供 CSV / JSON 导入场景的单事务批量写入能力。
调用方（services/backup.py）负责去重规划与校验，本模块只负责事务性落库。
"""

from __future__ import annotations

from collections.abc import Sequence

from ..extensions import db
from ..models import Category, Subscription
from ._common import SUBSCRIPTION_COLUMNS


def batch_import(
    categories: Sequence[dict], subscriptions: Sequence[dict]
) -> tuple[bool, str | None, bool]:
    """在单个数据库事务中批量写入分类与订阅。

    Parameters
    ----------
    categories : list[dict]
        已归一化的分类字典列表（id, user_id, name, icon, sort_order）。
    subscriptions : list[dict]
        已归一化的订阅字典列表（列与 SUBSCRIPTION_COLUMNS 一致）。

    Returns
    -------
    tuple[bool, str | None, bool]
        (success, error_message, atomic)。
        - 成功: (True, None, True)
        - 失败: (False, str(exc), True)  —— 事务已回滚。
        - 空数据: (True, None, True)
    """
    if not categories and not subscriptions:
        return True, None, True
    try:
        for category in categories:
            db.session.add(
                Category(
                    id=category["id"],
                    user_id=category["user_id"],
                    name=category["name"],
                    icon=category.get("icon"),
                    sort_order=category.get("sort_order", 0),
                )
            )
        for sub in subscriptions:
            db.session.add(
                Subscription(**{col: sub.get(col) for col in SUBSCRIPTION_COLUMNS})
            )
        db.session.commit()
        return True, None, True
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        return False, str(exc), True
