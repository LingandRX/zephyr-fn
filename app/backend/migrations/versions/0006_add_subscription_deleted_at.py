"""在 subscriptions 表中增加 deleted_at 字段支持软删除。

Revision ID: 0006_add_subscription_deleted_at
Revises: 0005_add_payments_cny_and_rate
Create Date: 2026-09-12
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0006_add_subscription_deleted_at"
down_revision = "0005_add_payments_cny_and_rate"
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
    # 1. 幂等添加 deleted_at 列
    if not _column_exists("subscriptions", "deleted_at"):
        op.execute("ALTER TABLE subscriptions ADD COLUMN deleted_at TEXT")

    # 2. 幂等创建复合索引以加速未删除订阅的查询
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sub_user_deleted
        ON subscriptions(user_id, deleted_at)
    """)


def downgrade() -> None:
    pass
