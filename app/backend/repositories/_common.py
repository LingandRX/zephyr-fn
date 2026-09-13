"""仓储层公共工具函数与常量定义。

提供 ID 生成、时间戳、类型转换、密钥占位符判断等基础能力，
以及订阅/设置的字段白名单常量。供各子模块按需导入。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

# --------------------------------------------------------------------------- #
# 订阅字段常量
# --------------------------------------------------------------------------- #

# 订阅全量列（写入顺序固定，供 raw 导入/替换使用）
SUBSCRIPTION_COLUMNS = (
    "id",
    "user_id",
    "name",
    "amount",
    "currency",
    "actual_amount",
    "category_id",
    "notes",
    "period_type",
    "custom_period_value",
    "custom_period_unit",
    "auto_renew",
    "sharing_role",
    "sharing_count",
    "start_date",
    "first_payment_date",
    "current_period_start",
    "current_period_end",
    "next_due_date",
    "next_billing_date",
    "last_payment_date",
    "renewal_confirmed",
    "lifecycle",
    "renewal_policy",
    "billing_status",
    "grace_period_ends_at",
    "cancelled_at",
    "paused_at",
    "deleted_at",
    "sync_version",
    "created_at",
    "updated_at",
)

# 可更新的订阅字段白名单
SUBSCRIPTION_FIELDS = (
    "name",
    "amount",
    "currency",
    "actual_amount",
    "category_id",
    "notes",
    "period_type",
    "custom_period_value",
    "custom_period_unit",
    "auto_renew",
    "sharing_role",
    "sharing_count",
    "start_date",
    "first_payment_date",
    "current_period_start",
    "current_period_end",
    "next_due_date",
    "next_billing_date",
    "last_payment_date",
    "renewal_confirmed",
    "lifecycle",
    "renewal_policy",
    "billing_status",
    "grace_period_ends_at",
    "cancelled_at",
    "paused_at",
)

# --------------------------------------------------------------------------- #
# 设置字段常量
# --------------------------------------------------------------------------- #

# 设置字段白名单
SETTINGS_FIELDS = (
    "dark_mode",
    "default_currency",
    "exchange_rate_usd",
    "exchange_rate_hkd",
    "notification_days",
    "notification_time",
    "do_not_disturb_start",
    "do_not_disturb_end",
    "auto_start",
    "tray_mode",
    "email_enabled",
    "smtp_host",
    "smtp_port",
    "smtp_username",
    "smtp_password",
    "smtp_from_address",
    "email_template",
    "notification_enabled",
    "pushplus_enabled",
    "pushplus_token",
    "pushplus_smtp_host",
    "pushplus_smtp_port",
    "pushplus_smtp_username",
    "pushplus_smtp_password",
    "pushplus_smtp_from_address",
    "last_check_date",
    "last_rate_update",
)

_SECRET_SETTING_FIELDS = frozenset(
    {
        "smtp_password",
        "pushplus_token",
        "pushplus_smtp_password",
    }
)
_SECRET_MASK_EXACT = frozenset(
    {
        "***",
        "******",
        "********",
        "**********",
        "************",
        "••••",
        "••••••",
        "••••••••",
        "[redacted]",
        "[已配置]",
        "已配置",
        "configured",
    }
)


# --------------------------------------------------------------------------- #
# 通用工具函数
# --------------------------------------------------------------------------- #


def new_id() -> str:
    return uuid.uuid4().hex


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def is_secret_placeholder(value: Any) -> bool:
    """判断设置请求中的值是否表示"保持原密钥"。"""
    if value is None:
        return True
    text_value = str(value).strip()
    if not text_value:
        return True
    lowered = text_value.lower()
    if lowered in _SECRET_MASK_EXACT:
        return True
    if "已配置" in text_value or lowered in {"redacted", "masked"}:
        return True
    mask_chars = {"*", "•", "·", "●"}
    return len(text_value) >= 3 and all(char in mask_chars for char in text_value)
