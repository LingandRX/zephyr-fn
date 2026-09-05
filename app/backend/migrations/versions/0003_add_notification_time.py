"""添加每日固定推送时刻字段（notification_time）。

到期提醒调度从「每 1 小时轮询」改为「每天固定一个时刻推送」，
此迁移为 app_settings 新增 notification_time（HH:MM，默认 09:00）。

Revision ID: 0003_add_notification_time
Revises: 0002_add_pushplus_smtp
Create Date: 2026-08-29
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by alembic.
revision = "0003_add_notification_time"
down_revision = "0002_add_pushplus_smtp"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    """检查 SQLite 表中是否存在指定列。"""
    from alembic import context
    from sqlalchemy import text

    bind = context.get_bind()
    result = bind.execute(text(f"PRAGMA table_info({table})"))
    existing = {row[1] for row in result.fetchall()}
    return column in existing


def upgrade() -> None:
    # 每日固定推送时刻（幂等：跳过已存在的列）
    if not _column_exists("app_settings", "notification_time"):
        op.execute(
            "ALTER TABLE app_settings "
            "ADD COLUMN notification_time TEXT DEFAULT '09:00'"
        )


def downgrade() -> None:
    # SQLite 不支持 DROP COLUMN（直到 3.35.0），降级需要重建表
    # 这里仅作记录，实际降级需要更复杂的操作
    pass
