"""添加支付流水表并修改订阅表结构。

Revision ID: 0004_add_payments_table
Revises: 0003_add_notification_time
Create Date: 2026-09-12
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0004_add_payments_table"
down_revision = "0003_add_notification_time"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 创建支付流水表
    op.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id TEXT PRIMARY KEY,
            subscription_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            amount INTEGER NOT NULL,
            currency TEXT NOT NULL,
            paid_at TEXT NOT NULL,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            payment_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'success',
            external_txn_id TEXT,
            note TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # 2. 创建支付流水表索引
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_payment_user_date_status
        ON payments(user_id, paid_at, status)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_payment_sub_date
        ON payments(subscription_id, paid_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_payment_period
        ON payments(period_start, period_end)
    """)

    # 3. 修改订阅表结构 - 添加新字段
    # 注意：SQLite 不支持 ALTER TABLE ADD COLUMN IF NOT EXISTS
    # 我们需要先检查字段是否存在，如果不存在则添加

    # 添加 current_period_start 字段
    op.execute("""
        ALTER TABLE subscriptions ADD COLUMN current_period_start TEXT
    """)

    # 添加 current_period_end 字段
    op.execute("""
        ALTER TABLE subscriptions ADD COLUMN current_period_end TEXT
    """)

    # 添加 next_billing_date 字段
    op.execute("""
        ALTER TABLE subscriptions ADD COLUMN next_billing_date TEXT
    """)

    # 添加 last_payment_date 字段
    op.execute("""
        ALTER TABLE subscriptions ADD COLUMN last_payment_date TEXT
    """)

    # 添加 renewal_confirmed 字段
    op.execute("""
        ALTER TABLE subscriptions ADD COLUMN renewal_confirmed INTEGER NOT NULL DEFAULT 0
    """)

    # 添加 cancelled_at 字段
    op.execute("""
        ALTER TABLE subscriptions ADD COLUMN cancelled_at TEXT
    """)

    # 添加 paused_at 字段
    op.execute("""
        ALTER TABLE subscriptions ADD COLUMN paused_at TEXT
    """)

    # 4. 创建新的索引
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sub_period
        ON subscriptions(current_period_start, current_period_end)
    """)

    # 5. 数据迁移：为现有订阅设置初始值
    # 对于已有订阅，根据现有字段推导新字段的初始值
    op.execute("""
        UPDATE subscriptions
        SET
            current_period_start = COALESCE(first_payment_date, start_date),
            current_period_end = next_due_date,
            last_payment_date = first_payment_date,
            renewal_confirmed = CASE
                WHEN lifecycle = 'active' AND auto_renew = 0 THEN 0
                ELSE 1
            END
        WHERE current_period_start IS NULL
    """)

    # 6. 根据lifecycle状态设置cancelled_at和paused_at
    op.execute("""
        UPDATE subscriptions
        SET cancelled_at = updated_at
        WHERE lifecycle = 'canceled' AND cancelled_at IS NULL
    """)

    op.execute("""
        UPDATE subscriptions
        SET paused_at = updated_at
        WHERE lifecycle = 'paused' AND paused_at IS NULL
    """)

    # 7. 为现有订阅创建首次支付记录（如果first_payment_date存在）
    op.execute("""
        INSERT INTO payments (
            id,
            subscription_id,
            user_id,
            amount,
            currency,
            paid_at,
            period_start,
            period_end,
            payment_type,
            status,
            note,
            created_at
        )
        SELECT
            hex(randomblob(16)),
            s.id,
            s.user_id,
            s.amount,
            s.currency,
            s.first_payment_date,
            s.start_date,
            s.next_due_date,
            'first',
            'success',
            'migrated initial payment',
            s.created_at
        FROM subscriptions s
        WHERE s.first_payment_date IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM payments p
              WHERE p.subscription_id = s.id
                AND p.payment_type = 'first'
          )
    """)


def downgrade() -> None:
    # 删除支付流水表
    op.execute("DROP TABLE IF EXISTS payments")

    # 注意：SQLite 不支持 DROP COLUMN，所以我们不删除添加的字段
    # 在实际生产环境中，可能需要创建新表、迁移数据、删除旧表、重命名新表
    # 这里为了简单起见，我们只删除 payments 表
    pass
