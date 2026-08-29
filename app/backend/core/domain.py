"""领域逻辑：周期推进、续费策略、状态推导、输入校验与日历事件。"""
from __future__ import annotations

import math
import re
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from typing import Any

PERIOD_TYPES = ("month", "quarter", "year", "once", "custom")
CUSTOM_UNITS = ("day", "week", "month", "year")
RENEWAL_POLICIES = ("auto", "manual", "stop", "stop_on_expiry")
LIFECYCLES = ("active", "in_payment", "grace_period", "canceled", "ended", "expired")
CURRENCIES = ("CNY", "USD", "HKD")
BILLING_STATUSES = ("normal", "paid", "overdue")

# 到期状态阈值：到期前 N 天内视为"即将到期"（与参考项目一致，7 天）
EXPIRING_THRESHOLD_DAYS = 7
MAX_SUBSCRIPTION_NAME_LENGTH = 200

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_INTEGER_RE = re.compile(r"^[+-]?\d+$")
_MISSING = object()

# 导入导出使用中文标签；领域层同时接受这些标签，保证 JSON/CSV 导入和
# API 创建/更新最终落到同一套内部枚举值。
_RENEWAL_ALIASES = {
    "自动续费": "auto",
    "手动续费": "manual",
    "到期停止": "stop",
    "到期后停止": "stop_on_expiry",
}
_LIFECYCLE_ALIASES = {
    "活跃": "active",
    "即将到期": "active",
    "待支付": "in_payment",
    "宽限期": "grace_period",
    "已取消": "canceled",
    "已结束": "ended",
    "已过期": "expired",
}
_BILLING_ALIASES = {
    "正常": "normal",
    "已支付": "paid",
    "逾期": "overdue",
}


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    next_month = date(year, month + 1, 1)
    return (next_month - date(year, month, 1)).days


def add_months(d: date, months: int) -> date:
    """按日历月推进，月末日期保持月末锚点。

    例如 2026-01-31 -> 2026-02-28 -> 2026-03-31。这样月末订阅在
    ``add_one_period`` / ``sub_one_period`` 之间不会逐月漂移到 28 号。
    非月末日期仍然按目标月钳制，例如 2026-01-30 -> 2026-02-28。
    """
    idx = d.month - 1 + months
    year = d.year + idx // 12
    month = idx % 12 + 1
    target_last_day = _days_in_month(year, month)
    source_is_month_end = d.day == _days_in_month(d.year, d.month)
    day = target_last_day if source_is_month_end else min(d.day, target_last_day)
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
    """往回退一期；月末日期与 ``add_one_period`` 使用相同锚点规则。"""
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


# --------------------------------------------------------------------------- #
# 领域输入校验与归一化
# --------------------------------------------------------------------------- #


def normalize_bool(value: Any, field: str = "布尔字段", default: bool | None = None) -> bool:
    """严格解析布尔值，拒绝未知字符串和任意非 0/1 数字。"""
    if value is None or (isinstance(value, str) and not value.strip()):
        if default is not None:
            return default
        raise ValueError(f"{field}不能为空")
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, float) and math.isfinite(value) and value in (0.0, 1.0):
        return bool(int(value))
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("1", "true", "yes", "on"):
            return True
        if normalized in ("0", "false", "no", "off"):
            return False
    raise ValueError(f"{field}必须是布尔值")


def normalize_non_negative_int(
    value: Any,
    field: str,
    *,
    allow_none: bool = False,
    default: int | None | object = _MISSING,
) -> int | None:
    """严格解析非负整数，金额等字段禁止静默截断或把非法值变成 0。"""
    if value is None or (isinstance(value, str) and not value.strip()):
        if default is not _MISSING:
            value = default
        elif allow_none:
            return None
        else:
            raise ValueError(f"{field}不能为空")
    if value is None:
        if allow_none:
            return None
        raise ValueError(f"{field}不能为空")
    if isinstance(value, bool):
        raise ValueError(f"{field}必须是整数")
    if isinstance(value, int):
        result = value
    elif isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise ValueError(f"{field}必须是整数")
        result = int(value)
    elif isinstance(value, str) and _INTEGER_RE.fullmatch(value.strip()):
        result = int(value.strip())
    else:
        raise ValueError(f"{field}必须是整数")
    if result < 0:
        raise ValueError(f"{field}不能为负数")
    return result


def normalize_positive_int(value: Any, field: str) -> int:
    result = normalize_non_negative_int(value, field)
    if result is None or result <= 0:
        raise ValueError(f"{field}必须大于0")
    return result


def normalize_date(
    value: Any,
    field: str = "日期",
    *,
    allow_none: bool = True,
    default: Any = _MISSING,
) -> str | None:
    """只接受 ``YYYY-MM-DD`` 或 ``date``，不再截断任意字符串前 10 位。"""
    if value is None or (isinstance(value, str) and not value.strip()):
        if default is not _MISSING:
            return normalize_date(default, field, allow_none=False)
        if allow_none:
            return None
        raise ValueError(f"{field}不能为空")
    if isinstance(value, datetime):
        # datetime 是 date 的子类，但日期字段不能悄悄丢弃时分秒。
        raise ValueError(f"{field}必须是YYYY-MM-DD")
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str):
        raise ValueError(f"{field}必须是YYYY-MM-DD")
    text = value.strip()
    if not _DATE_RE.fullmatch(text):
        raise ValueError(f"{field}必须是YYYY-MM-DD")
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field}不是有效日期") from exc


def _normalize_enum(
    value: Any,
    choices: tuple[str, ...],
    field: str,
    *,
    aliases: Mapping[str, str] | None = None,
    default: str | None | object = _MISSING,
) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        if default is not _MISSING:
            return default
        raise ValueError(f"{field}不能为空")
    if not isinstance(value, str):
        raise ValueError(f"{field}值无效")
    normalized = value.strip()
    normalized = (aliases or {}).get(normalized, normalized)
    if normalized not in choices:
        raise ValueError(f"{field}值无效: {value}")
    return normalized


def normalize_currency(value: Any = None, *, default: str = "CNY") -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        value = default
    if not isinstance(value, str):
        raise ValueError("货币值无效")
    normalized = value.strip().upper()
    if normalized not in CURRENCIES:
        raise ValueError(f"不支持的货币: {normalized}")
    return normalized


def normalize_period_type(value: Any = None, *, default: str = "month") -> str:
    return _normalize_enum(value, PERIOD_TYPES, "周期类型", default=default)  # type: ignore[return-value]


def normalize_custom_period(
    period_type: str,
    custom_value: Any = None,
    custom_unit: Any = None,
) -> tuple[int | None, str | None]:
    if period_type != "custom":
        return None, None
    value = normalize_positive_int(custom_value, "自定义周期值")
    unit = _normalize_enum(custom_unit, CUSTOM_UNITS, "自定义周期单位")
    return value, unit


def normalize_renewal_policy(value: Any = None, *, default: str | None = None) -> str | None:
    return _normalize_enum(
        value,
        RENEWAL_POLICIES,
        "续费策略",
        aliases=_RENEWAL_ALIASES,
        default=default,
    )


def normalize_lifecycle(value: Any = None, *, default: str = "active") -> str:
    return _normalize_enum(
        value,
        LIFECYCLES,
        "生命周期",
        aliases=_LIFECYCLE_ALIASES,
        default=default,
    )  # type: ignore[return-value]


def normalize_billing_status(value: Any = None, *, default: str = "normal") -> str:
    return _normalize_enum(
        value,
        BILLING_STATUSES,
        "账单状态",
        aliases=_BILLING_ALIASES,
        default=default,
    )  # type: ignore[return-value]


def normalize_renewal_on_create(
    auto_renew: bool, explicit_policy: str | None
) -> tuple[bool, str]:
    """创建时统一 auto_renew 与 renewal_policy，并严格校验显式策略。"""
    auto = normalize_bool(auto_renew, "自动续费")
    policy = normalize_renewal_policy(explicit_policy, default=None)
    if policy is not None:
        return policy == "auto", policy
    return auto, "auto" if auto else "manual"


def resolve_renewal_on_update(
    current_auto_renew: bool,
    current_policy: str,
    update_auto_renew: bool | None,
    update_policy: str | None,
    period_type: str | None = None,
) -> tuple[bool, str]:
    """更新时统一 auto_renew 与 renewal_policy。

    显式 ``renewal_policy`` 优先；只更新 ``auto_renew`` 时由布尔值推导策略。
    一次性订阅永远不自动续费，并统一为 ``manual``。
    """
    current_auto = normalize_bool(current_auto_renew, "当前自动续费")
    current = normalize_renewal_policy(current_policy, default="manual") or "manual"
    policy = normalize_renewal_policy(update_policy, default=None)
    auto = (
        normalize_bool(update_auto_renew, "自动续费")
        if update_auto_renew is not None
        else None
    )
    if period_type == "once":
        return False, "manual"
    if policy is not None:
        return policy == "auto", policy
    if auto is not None:
        return auto, "auto" if auto else "manual"
    return current_auto, current


def normalize_subscription_data(
    data: Mapping[str, Any],
    *,
    defaults: Mapping[str, Any] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """统一校验订阅核心字段。

    ``defaults`` 用于创建、更新合并和导入场景；传入的值仍会经过同一套
    严格校验。函数只负责领域字段，分类、备注和时间戳等持久化细节由 db 层处理。
    """
    values: dict[str, Any] = dict(defaults or {})
    values.update(dict(data))
    today = today or date.today()

    name_value = values.get("name")
    name = str(name_value or "").strip()
    if not name:
        raise ValueError("名称不能为空")
    if len(name) > MAX_SUBSCRIPTION_NAME_LENGTH:
        raise ValueError(f"名称不能超过{MAX_SUBSCRIPTION_NAME_LENGTH}字")

    amount = normalize_non_negative_int(values.get("amount", 0), "金额", default=0)
    actual_amount = normalize_non_negative_int(
        values.get("actual_amount"), "实际金额", allow_none=True
    )
    currency = normalize_currency(values.get("currency"), default="CNY")
    period_type = normalize_period_type(values.get("period_type"), default="month")
    if period_type != "custom":
        for field in ("custom_period_value", "custom_period_unit"):
            value = values.get(field)
            if value not in (None, ""):
                raise ValueError(f"{field}仅适用于custom周期")
    custom_value, custom_unit = normalize_custom_period(
        period_type,
        values.get("custom_period_value"),
        values.get("custom_period_unit"),
    )

    auto_renew = normalize_bool(values.get("auto_renew", True), "自动续费", default=True)
    explicit_policy = values.get("renewal_policy")
    auto_renew, renewal_policy = normalize_renewal_on_create(auto_renew, explicit_policy)
    if period_type == "once":
        auto_renew, renewal_policy = False, "manual"

    lifecycle = normalize_lifecycle(values.get("lifecycle"), default="active")
    billing_status = normalize_billing_status(
        values.get("billing_status"), default="normal"
    )

    start_date = normalize_date(
        values.get("start_date"),
        "开始日期",
        allow_none=False,
        default=today,
    )
    first_payment_date = normalize_date(values.get("first_payment_date"), "首次付款日")
    next_due_date = normalize_date(values.get("next_due_date"), "下次到期日")
    grace_period_ends_at = normalize_date(
        values.get("grace_period_ends_at"), "宽限期结束日期"
    )

    return {
        "name": name,
        "amount": amount,
        "currency": currency,
        "actual_amount": actual_amount,
        "period_type": period_type,
        "custom_period_value": custom_value,
        "custom_period_unit": custom_unit,
        "auto_renew": auto_renew,
        "renewal_policy": renewal_policy,
        "lifecycle": lifecycle,
        "billing_status": billing_status,
        "start_date": start_date,
        "first_payment_date": first_payment_date,
        "next_due_date": next_due_date,
        "grace_period_ends_at": grace_period_ends_at,
    }


def should_auto_renew_on_wake(auto_renew: bool, renewal_policy: str) -> bool:
    return auto_renew and renewal_policy == "auto"


def derive_status(lifecycle: str, next_due_date: str | None, today: date | None = None) -> str:
    """派生订阅状态。

    ``active`` 订阅在到期日之后显示为 ``expired``，而不是继续显示为
    ``expiring``；数据库中明确的 ``ended`` 等生命周期状态保持原值。
    """
    today = today or date.today()
    if lifecycle == "active":
        if next_due_date:
            try:
                due = date.fromisoformat(next_due_date)
            except (TypeError, ValueError):
                # 数据库迁移前可能存在旧的脏日期；展示层宁可显示 active，
                # 也不要把无法解析的数据误判为即将到期。
                return "active"
            days = (due - today).days
            if days < 0:
                return "expired"
            if days <= EXPIRING_THRESHOLD_DAYS:
                return "expiring"
        return "active"
    if lifecycle == "in_payment":
        return "in_payment"
    if lifecycle == "grace_period":
        return "grace_period"
    if lifecycle == "canceled":
        return "canceled"
    if lifecycle == "ended":
        return "ended"
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
        try:
            return date.fromisoformat(updated_at[:10])
        except (TypeError, ValueError):
            return None
    return None


def is_calendar_event_visible(lifecycle: str, updated_at: str | None, event_date: date) -> bool:
    if not is_calendar_trackable(lifecycle):
        return False
    term = calendar_termination_date(lifecycle, updated_at)
    return term is None or event_date <= term

