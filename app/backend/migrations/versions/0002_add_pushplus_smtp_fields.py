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


def upgrade() -> None:
    # 添加 PushPlus 专用的 SMTP 配置字段
    op.execute("ALTER TABLE app_settings ADD COLUMN pushplus_smtp_host TEXT")
    op.execute("ALTER TABLE app_settings ADD COLUMN pushplus_smtp_port INTEGER")
    op.execute("ALTER TABLE app_settings ADD COLUMN pushplus_smtp_username TEXT")
    op.execute("ALTER TABLE app_settings ADD COLUMN pushplus_smtp_password TEXT")
    op.execute("ALTER TABLE app_settings ADD COLUMN pushplus_smtp_from_address TEXT")


def downgrade() -> None:
    # SQLite 不支持 DROP COLUMN（直到 3.35.0），降级需要重建表
    # 这里仅作记录，实际降级需要更复杂的操作
    pass
