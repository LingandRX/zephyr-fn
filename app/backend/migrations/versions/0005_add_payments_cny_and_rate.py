"""在 payments 表中增加 exchange_rate（汇率快照）和 amount_cny（本位币金额）字段。

Revision ID: 0005_add_payments_cny_and_rate
Revises: 0004_add_payments_table
Create Date: 2026-09-12
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "0005_add_payments_cny_and_rate"
down_revision = "0004_add_payments_table"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    """检查 SQLite 表中是否存在指定列。"""
    from alembic import context

    bind = context.get_bind()
    result = bind.execute(text(f"PRAGMA table_info({table})"))
    existing = {row[1] for row in result.fetchall()}
    return column in existing


def upgrade() -> None:
    # 1. 检查并添加 exchange_rate 字段
    if not _column_exists("payments", "exchange_rate"):
        op.execute("ALTER TABLE payments ADD COLUMN exchange_rate REAL NOT NULL DEFAULT 1.0")

    # 2. 检查并添加 amount_cny 字段
    if not _column_exists("payments", "amount_cny"):
        op.execute("ALTER TABLE payments ADD COLUMN amount_cny INTEGER NOT NULL DEFAULT 0")

    # 3. 针对存量支付数据，依据当时的设置汇率补齐快照字段
    from alembic import context

    bind = context.get_bind()
    usd_rate = 7.2
    hkd_rate = 0.92
    try:
        settings_row = bind.execute(
            text("SELECT exchange_rate_usd, exchange_rate_hkd FROM app_settings WHERE id = 1")
        ).fetchone()
        if settings_row:
            if settings_row[0]:
                usd_rate = float(settings_row[0])
            if settings_row[1]:
                hkd_rate = float(settings_row[1])
    except Exception:
        pass

    # 3.1 CNY 货币，汇率恒为 1.0，amount_cny 等于原始金额
    op.execute("""
        UPDATE payments
        SET exchange_rate = 1.0,
            amount_cny = amount
        WHERE (currency = 'CNY' OR currency IS NULL)
          AND (amount_cny = 0 OR amount_cny IS NULL)
    """)

    # 3.2 USD 货币，记录快照汇率及换算后的整型分
    op.execute(f"""
        UPDATE payments
        SET exchange_rate = {usd_rate},
            amount_cny = CAST(ROUND(amount * {usd_rate}) AS INTEGER)
        WHERE currency = 'USD'
          AND (amount_cny = 0 OR amount_cny IS NULL)
    """)

    # 3.3 HKD 货币
    op.execute(f"""
        UPDATE payments
        SET exchange_rate = {hkd_rate},
            amount_cny = CAST(ROUND(amount * {hkd_rate}) AS INTEGER)
        WHERE currency = 'HKD'
          AND (amount_cny = 0 OR amount_cny IS NULL)
    """)

    # 3.4 其它非标准货币默认按 1.0 折算
    op.execute("""
        UPDATE payments
        SET exchange_rate = 1.0,
            amount_cny = amount
        WHERE currency NOT IN ('CNY', 'USD', 'HKD')
          AND (amount_cny = 0 OR amount_cny IS NULL)
    """)


def downgrade() -> None:
    # SQLite ALTER TABLE 不支持安全直接 DROP COLUMN，生产中可通过备份/重建表降级
    pass
