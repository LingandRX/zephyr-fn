"""领域逻辑：周期推进、续费策略、状态推导、日历事件（移植自 zephyr-tarui）。"""
from __future__ import annotations

from datetime import date, timedelta

PERIOD_TYPES = ("month", "quarter", "year", "once", "custom")
CUSTOM_UNITS = ("day", "week", "month", "year")
RENEWAL_POLICIES = ("auto", "manual", "stop", "stop_on_expiry")
LIFECYCLES = ("active", "in_payment", "grace_period", "canceled", "ended", "expired")

# 到期状态阈值：到期前 N 天内视为"即将到期"（与参考项目一致，7 天）
EXPIRING_THRESHOLD_DAYS = 7


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    next_month = date(year, month + 1, 1)
    return (next_month - date(year, month, 1)).days


def add_months(d: date, months: int) -> date:
    """按日历月推进，月末日期钳制到目标月最后一天（与 chrono/date-fns 一致）。"""
    idx = d.month - 1 + months
    year = d.year + idx // 12
    month = idx % 12 + 1
    day = min(d.day, _days_in_month(year, month))
    return date(year, month, day)


def add_one_period(
    d: date, period_type: str, custom_value: int | None = None,
    custom_unit: str | None = None,
) -> date | None:
    """按订阅周期推进一期。一次性(once)订阅没有后续周期，返回 None。"""
    if period_type == "month":
        return add_months(d, 1)
    if period_type == "quarter":
        return add_months(d, 3)
    if period_type == "year":
        return add_months(d, 12)
    if period_type == "once":
        return None
    if period_type == "custom":
        value = max(1, int(custom_value or 1))
        unit = custom_unit or "month"
        if unit == "day":
            return d + timedelta(days=value)
        if unit == "week":
            return d + timedelta(weeks=value)
        if unit == "month":
            return add_months(d, value)
        if unit == "year":
            return add_months(d, value * 12)
    return None


def sub_one_period(
    d: date, period_type: str, custom_value: int | None = None,
    custom_unit: str | None = None,
) -> date | None:
    """往回退一期（add_one_period 的逆运算）。"""
    if period_type == "month":
        return add_months(d, -1)
    if period_type == "quarter":
        return add_months(d, -3)
    if period_type == "year":
        return add_months(d, -12)
    if period_type == "once":
        return None
    if period_type == "custom":
        value = max(1, int(custom_value or 1))
        unit = custom_unit or "month"
        if unit == "day":
            return d - timedelta(days=value)
        if unit == "week":
            return d - timedelta(weeks=value)
        if unit == "month":
            return add_months(d, -value)
        if unit == "year":
            return add_months(d, -value * 12)
    return None


def normalize_renewal_on_create(
    auto_renew: bool, explicit_policy: str | None
) -> tuple[bool, str]:
    """创建时统一 auto_renew 与 renewal_policy。"""
    if explicit_policy in RENEWAL_POLICIES:
        return (explicit_policy == "auto", explicit_policy)
    policy = "auto" if auto_renew else "manual"
    return (auto_renew, policy)


def resolve_renewal_on_update(
    current_auto_renew: bool, current_policy: str,
    update_auto_renew: bool | None, update_policy: str | None,
) -> tuple[bool, str]:
    """更新时统一 auto_renew 与 renewal_policy（显式 renewal_policy 优先）。"""
    if update_policy:
        return (update_policy == "auto", update_policy)
    if update_auto_renew is not None:
        policy = "auto" if update_auto_renew else "manual"
        return (update_auto_renew, policy)
    return (current_auto_renew, current_policy)


def should_auto_renew_on_wake(auto_renew: bool, renewal_policy: str) -> bool:
    return auto_renew and renewal_policy == "auto"


def derive_status(lifecycle: str, next_due_date: str | None, today: date | None = None) -> str:
    """派生订阅状态（active → expiring 等），移植自 SubscriptionStatus::from_subscription。"""
    today = today or date.today()
    if lifecycle == "active":
        if next_due_date:
            try:
                days = (date.fromisoformat(next_due_date) - today).days
            except ValueError:
                days = 0
            if days <= EXPIRING_THRESHOLD_DAYS:
                return "expiring"
        return "active"
    if lifecycle == "in_payment":
        return "in_payment"
    if lifecycle == "grace_period":
        return "grace_period"
    if lifecycle == "canceled":
        return "canceled"
    if lifecycle == "expired":
        return "expired"
    return "active"


STATUS_LABELS = {
    "active": "活跃",
    "expiring": "即将到期",
    "in_payment": "待支付",
    "grace_period": "宽限期",
    "canceled": "已取消",
    "ended": "已结束",
    "expired": "已过期",
}

STATUS_COLORS = {
    "active": "#22C55E",
    "expiring": "#F59E0B",
    "in_payment": "#3B82F6",
    "grace_period": "#F97316",
    "canceled": "#6B7280",
    "ended": "#6B7280",
    "expired": "#EF4444",
}

PERIOD_LABELS = {
    "month": "月付",
    "quarter": "季付",
    "year": "年付",
    "once": "一次性",
    "custom": "自定义",
}

CURRENCY_SYMBOLS = {"CNY": "¥", "USD": "$", "HKD": "HK$"}


def calendar_due_event_type(renewal_policy: str) -> str:
    return "service_end" if renewal_policy in ("stop", "stop_on_expiry") else "due_date"


def is_calendar_trackable(lifecycle: str) -> bool:
    return lifecycle in ("active", "in_payment", "grace_period",
                         "canceled", "ended", "expired")


def calendar_termination_date(lifecycle: str, updated_at: str | None) -> date | None:
    if lifecycle in ("canceled", "ended", "expired") and updated_at:
        # updated_at 形如 2026-07-01T12:00:00Z，取日期部分
        return date.fromisoformat(updated_at[:10])
    return None


def is_calendar_event_visible(lifecycle: str, updated_at: str | None, event_date: date) -> bool:
    if not is_calendar_trackable(lifecycle):
        return False
    term = calendar_termination_date(lifecycle, updated_at)
    return term is None or event_date <= term
