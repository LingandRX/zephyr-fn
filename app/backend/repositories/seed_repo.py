"""用户播种仓储：记录哪些用户已补种过默认分类。"""

from __future__ import annotations

from ..extensions import db
from ..models import SeededUser
from ._common import now_utc


def is_user_seeded(user_id: str) -> bool:
    return db.session.get(SeededUser, user_id) is not None


def mark_user_seeded(user_id: str) -> None:
    db.session.add(SeededUser(user_id=user_id, seeded_at=now_utc()))
    db.session.commit()
