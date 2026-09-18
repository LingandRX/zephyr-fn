"""在 app_settings 表中增加订阅模板远程源同步字段。

Revision ID: 0007_add_template_sync_fields
Revises: 0006_add_subscription_deleted_at
Create Date: 2026-09-18
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0007_add_template_sync_fields"
down_revision = "0006_add_subscription_deleted_at"
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
    if not _column_exists("app_settings", "template_sync_url"):
        op.execute("ALTER TABLE app_settings ADD COLUMN template_sync_url TEXT")

    if not _column_exists("app_settings", "template_auto_sync"):
        op.execute("ALTER TABLE app_settings ADD COLUMN template_auto_sync INTEGER NOT NULL DEFAULT 0")

    if not _column_exists("app_settings", "template_last_synced_at"):
        op.execute("ALTER TABLE app_settings ADD COLUMN template_last_synced_at TEXT")


def downgrade() -> None:
    pass
