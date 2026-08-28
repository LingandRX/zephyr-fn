"""基线迁移：与旧版手写迁移 v11 的最终 schema 完全一致。

设计说明（重要）：
- 全部 DDL 使用 ``IF NOT EXISTS`` 守卫，可安全地在两种场景执行：
  1. 全新数据库：创建全部表与索引；
  2. 存量旧库：storage/bootstrap 已把旧库就地升级到 v11 基线，
     此处逐条跳过已存在的对象，仅收敛 Alembic 版本记录。
- 后续 schema 演进一律在此基线之上新增迁移（flask db migrate 生成）。

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-28
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 分类
    op.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT 'local',
            name TEXT NOT NULL,
            icon TEXT,
            sort_order INTEGER DEFAULT 0
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_cat_user_name
        ON categories(user_id, name COLLATE NOCASE)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_cat_user_sort
        ON categories(user_id, sort_order)
    """)

    # 订阅
    op.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT 'local',
            name TEXT NOT NULL,
            amount INTEGER NOT NULL,
            currency TEXT NOT NULL DEFAULT 'CNY',
            actual_amount INTEGER,
            category_id TEXT,
            notes TEXT,
            period_type TEXT NOT NULL,
            custom_period_value INTEGER,
            custom_period_unit TEXT,
            auto_renew INTEGER NOT NULL DEFAULT 1,
            sharing_role TEXT,
            sharing_count INTEGER,
            start_date TEXT NOT NULL,
            first_payment_date TEXT,
            next_due_date TEXT,
            lifecycle TEXT NOT NULL DEFAULT 'active',
            renewal_policy TEXT NOT NULL DEFAULT 'auto',
            billing_status TEXT NOT NULL DEFAULT 'normal',
            grace_period_ends_at TEXT,
            sync_version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_sub_user ON subscriptions(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sub_next ON subscriptions(next_due_date)")

    # 全局设置（单行约束）
    op.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            dark_mode TEXT NOT NULL DEFAULT 'system',
            default_currency TEXT NOT NULL DEFAULT 'CNY',
            exchange_rate_usd REAL NOT NULL DEFAULT 7.2,
            exchange_rate_hkd REAL NOT NULL DEFAULT 0.92,
            notification_days INTEGER NOT NULL DEFAULT 7,
            do_not_disturb_start TEXT,
            do_not_disturb_end TEXT,
            auto_start INTEGER NOT NULL DEFAULT 0,
            tray_mode INTEGER NOT NULL DEFAULT 1,
            email_enabled INTEGER NOT NULL DEFAULT 0,
            smtp_host TEXT,
            smtp_port INTEGER,
            smtp_username TEXT,
            smtp_password TEXT,
            smtp_from_address TEXT,
            email_template TEXT NOT NULL DEFAULT 'default',
            notification_enabled INTEGER NOT NULL DEFAULT 1,
            pushplus_enabled INTEGER NOT NULL DEFAULT 0,
            pushplus_token TEXT,
            last_check_date TEXT,
            last_rate_update TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # 邮件日志
    op.execute("""
        CREATE TABLE IF NOT EXISTS email_logs (
            id TEXT PRIMARY KEY,
            to_address TEXT NOT NULL,
            subject TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            error_message TEXT,
            sent_at TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # 通知日志（含幂等唯一约束）
    op.execute("""
        CREATE TABLE IF NOT EXISTS notification_logs (
            id TEXT PRIMARY KEY,
            subscription_id TEXT NOT NULL,
            notification_date TEXT NOT NULL,
            channel TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'sent',
            error_message TEXT,
            created_at TEXT NOT NULL
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_notif_sub_date
        ON notification_logs(subscription_id, notification_date)
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_notification_logs_identity
        ON notification_logs(subscription_id, notification_date, channel)
    """)

    # 默认分类补种标记
    op.execute("""
        CREATE TABLE IF NOT EXISTS seeded_users (
            user_id TEXT PRIMARY KEY,
            seeded_at TEXT NOT NULL
        )
    """)


def downgrade() -> None:
    """基线不回滚（旧库升级路径依赖本基线）；如需重建请从备份恢复。"""
    pass
