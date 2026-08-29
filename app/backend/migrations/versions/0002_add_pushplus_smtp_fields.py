"""添加 PushPlus 专用 SMTP 配置字段。

PushPlus 支持通过邮件方式发送消息到 {token}@yp9.cn。
此迁移将 PushPlus 的 SMTP 配置与邮件通知的 SMTP 配置分离，
允许用户为两者使用不同的邮件服务器。

Revision ID: 0002_add_pushplus_smtp
Revises: 0001_baseline
Create Date: 2026-08-29
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by alembic.
revision = "0002_add_pushplus_smtp"
down_revision = "0001_baseline"
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
    # 添加 PushPlus 专用的 SMTP 配置字段（幂等：跳过已存在的列）
    columns = [
        ("pushplus_smtp_host", "TEXT"),
        ("pushplus_smtp_port", "INTEGER"),
        ("pushplus_smtp_username", "TEXT"),
        ("pushplus_smtp_password", "TEXT"),
        ("pushplus_smtp_from_address", "TEXT"),
    ]
    for col, dtype in columns:
        if not _column_exists("app_settings", col):
            op.execute(f"ALTER TABLE app_settings ADD COLUMN {col} {dtype}")


def downgrade() -> None:
    # SQLite 不支持 DROP COLUMN（直到 3.35.0），降级需要重建表
    # 这里仅作记录，实际降级需要更复杂的操作
    pass
