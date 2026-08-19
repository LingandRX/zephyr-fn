"""统计与日历服务（移植自 zephyr-tarui 的 services.rs）。

口径与参考项目一致：
- monthly_expense      每月名义支出（按周期折算，非自动续费只计首付月一次）
- monthly_actual_expense 本月实际到期支出（按到期日周期计数）
- yearly_expense       本年到期支出
- upcoming_30_days     未来 30 天到期金额合计
- category_stats       分类统计（按月/年）
- monthly_trend        近 12 个月趋势
- get_calendar_events  按月生成日历到期事件
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

import db
import domain


def _divide_round(amount: int, divisor: int) -> int:
    return round(amount / divisor) if divisor else 0


def _monthly_amount(sub: dict, mode: str) -> int:
    """单个订阅折算为每月金额（分）。"""
    amount = sub["actual_amount"] if (mode == "actual" and sub["actual_amount"]) else sub["amount"]
    period = sub["period_type"]
    if period == "month":
        return amount
    if period == "quarter":
        return _divide_round(amount, 3)
    if period == "year":
        return _divide_round(amount, 12)
    if period == "custom":
        unit = sub.get("custom_period_unit") or "month"
        value = max(1, int(sub.get("custom_period_value") or 1))
        months = {"day": value / 30.0, "week": value / 4.0,
                  "month": float(value), "year": float(value) * 12.0}.get(unit, 1.0)
        return _divide_round(amount, months) if months else amount
    return amount  # once：一次性按全额折算


def _yearly_amount(sub: dict, mode: str) -> int:
    amount = sub["actual_amount"] if (mode == "actual" and sub["actual_amount"]) else sub["amount"]
    period = sub["period_type"]
    if period == "month":
        return amount * 12
    if period == "quarter":
        return amount * 4
    if period == "year":
        return amount
    if period == "custom":
        unit = sub.get("custom_period_unit") or "month"
        value = max(1, int(sub.get("custom_period_value") or 1))
        periods_per_year = {
            "day": 365.0 / value,
            "week": 52.0 / value,
            "month": 12.0 / value,
            "year": 1.0 / value,
        }.get(unit, 1.0)
        return round(amount * periods_per_year)
    return amount  # once


def _convert_to_cny(amount: int, currency: str, settings: dict) -> int:
    usd_rate = settings.get("exchange_rate_usd") or 7.2
    hkd_rate = settings.get("exchange_rate_hkd") or 0.92
    if currency == "USD":
        return round(amount * usd_rate)
    if currency == "HKD":
        return round(amount * hkd_rate)
    return amount


def _to_default_currency(amount_cny: int, default_currency: str, settings: dict) -> int:
    """把人民币金额换算到默认货币。"""
    if default_currency == "CNY":
        return amount_cny
    usd_rate = settings.get("exchange_rate_usd") or 7.2
    hkd_rate = settings.get("exchange_rate_hkd") or 0.92
    if default_currency == "USD":
        return round(amount_cny / usd_rate) if usd_rate else amount_cny
    if default_currency == "HKD":
        return round(amount_cny / hkd_rate) if hkd_rate else amount_cny
    return amount_cny


def _add_months_clamped(d: date, months: int) -> date:
    return domain.add_months(d, months)


def _month_end(d: date) -> date:
    return domain.add_months(d.replace(day=1), 1) - timedelta(days=1)


def _count_cycles_in_range(sub: dict, range_start: date, range_end: date) -> int:
    """统计订阅在 [range_start, range_end] 区间内到期的周期数（移植 count_cycles_in_range）。"""
    if sub["period_type"] == "once":
        return 0
    try:
        start_date = date.fromisoformat(sub["start_date"])
    except ValueError:
        return 0
    first_due = domain.add_one_period(
        start_date, sub["period_type"], sub["custom_period_value"], sub["custom_period_unit"]
    )
    if first_due is None:
        return 0
    try:
        anchor = date.fromisoformat(sub["next_due_date"]) if sub["next_due_date"] else first_due
    except ValueError:
        anchor = first_due

    step = lambda d: domain.add_one_period(
        d, sub["period_type"], sub["custom_period_value"], sub["custom_period_unit"])
    back = lambda d: domain.sub_one_period(
        d, sub["period_type"], sub["custom_period_value"], sub["custom_period_unit"])

    guard = 0
    while anchor > range_end:
        guard += 1
        if guard > 5000:
            return 0
        prev = back(anchor)
        if prev is None:
            return 0
        anchor = prev
    while anchor > range_start and anchor > start_date:
        guard += 1
        if guard > 5000:
            return 0
        prev = back(anchor)
        if prev is None:
            break
        anchor = prev
    while anchor < range_start:
        guard += 1
        if guard > 5000:
            return 0
        nxt = step(anchor)
        if nxt is None:
            return 0
        anchor = nxt
    count = 0
    while anchor <= range_end:
        guard += 1
        if guard > 5000:
            break
        if anchor > start_date:
            count += 1
        nxt = step(anchor)
        if nxt is None:
            break
        anchor = nxt
    return count


def calculate_statistics(user_id: str, mode: str = "nominal") -> dict:
    subs = db.get_all_subscriptions(user_id)
    cats = {c["id"]: c for c in db.get_all_categories(user_id)}
    settings = db.get_app_settings()
    default_currency = settings.get("default_currency") or "CNY"

    now = date.today()
    month_starts = [domain.add_months(now.replace(day=1), -i) for i in range(11, -1, -1)]
    month_ends = [_month_end(m) for m in month_starts]

    monthly_expense = 0
    monthly_actual_expense = 0
    yearly_expense = 0
    upcoming_30_days = 0
    active_count = 0
    cat_monthly: dict[str, int] = {}
    cat_yearly: dict[str, int] = {}
    monthly_amounts: dict[str, int] = {}

    month_start = now.replace(day=1)
    month_end = _month_end(now)
    year_start = date(now.year, 1, 1)
    year_end = date(now.year, 12, 31)
    # 未来 30 天
    future_end = now + timedelta(days=30)

    for sub in subs:
        if sub["lifecycle"] not in ("active", "in_payment"):
            continue
        active_count += 1

        amount = sub["actual_amount"] if (mode == "actual" and sub["actual_amount"]) else sub["amount"]
        cny_amount = _convert_to_cny(amount, sub["currency"], settings)

        monthly_amount = _monthly_amount(sub, mode)
        cny_monthly = _convert_to_cny(monthly_amount, sub["currency"], settings)
        monthly_expense += cny_monthly

        if sub["auto_renew"]:
            monthly_actual_expense += _count_cycles_in_range(sub, month_start, month_end) * cny_amount
        else:
            pay_date = sub["first_payment_date"] or sub["start_date"]
            try:
                pd = date.fromisoformat(pay_date)
            except ValueError:
                pd = None
            if pd and pd.year == now.year and pd.month == now.month:
                monthly_actual_expense += cny_amount

        yearly_amount = _yearly_amount(sub, mode)
        cny_yearly = _convert_to_cny(yearly_amount, sub["currency"], settings)
        if sub["auto_renew"]:
            yearly_expense += _count_cycles_in_range(sub, year_start, year_end) * cny_amount
        else:
            pay_date = sub["first_payment_date"] or sub["start_date"]
            try:
                pd = date.fromisoformat(pay_date)
            except ValueError:
                pd = None
            if pd and pd.year == now.year:
                yearly_expense += cny_amount

        if sub.get("next_due_date"):
            try:
                due = date.fromisoformat(sub["next_due_date"])
            except ValueError:
                due = None
            if due and now <= due <= future_end:
                upcoming_30_days += cny_amount

        cat_id = sub["category_id"] or "uncategorized"
        cat_monthly[cat_id] = cat_monthly.get(cat_id, 0) + cny_monthly
        cat_yearly[cat_id] = cat_yearly.get(cat_id, 0) + cny_yearly

        # 月度趋势（按实际到期/发生扣费统计）
        for ms, me in zip(month_starts, month_ends):
            m_key = ms.strftime("%Y-%m")
            if sub["auto_renew"]:
                cycles = _count_cycles_in_range(sub, ms, me)
                if cycles > 0:
                    monthly_amounts[m_key] = (
                        monthly_amounts.get(m_key, 0) + cycles * cny_amount
                    )
            else:
                pay_date = sub["first_payment_date"] or sub["start_date"]
                try:
                    pd = date.fromisoformat(pay_date)
                except (ValueError, TypeError):
                    pd = None
                if pd and ms <= pd <= me:
                    monthly_amounts[m_key] = (
                        monthly_amounts.get(m_key, 0) + cny_amount
                    )

    category_stats = []
    for cat_id, amount_cny in cat_monthly.items():
        name = cats.get(cat_id, {}).get("name", "未分类") if cat_id != "uncategorized" else "未分类"
        yearly_cny = cat_yearly.get(cat_id, 0)
        percentage = round(amount_cny / monthly_expense * 100, 1) if monthly_expense else 0.0
        category_stats.append({
            "category_id": cat_id,
            "category_name": name,
            "amount": _to_default_currency(amount_cny, default_currency, settings),
            "yearly_amount": _to_default_currency(yearly_cny, default_currency, settings),
            "percentage": percentage,
        })
    category_stats.sort(key=lambda x: -x["amount"])

    monthly_trend = [
        {"month": ms.strftime("%Y-%m"),
         "amount": _to_default_currency(monthly_amounts.get(ms.strftime("%Y-%m"), 0),
                                        default_currency, settings)}
        for ms in month_starts
    ]

    return {
        "monthly_expense": _to_default_currency(monthly_expense, default_currency, settings),
        "monthly_actual_expense": _to_default_currency(monthly_actual_expense, default_currency, settings),
        "yearly_expense": _to_default_currency(yearly_expense, default_currency, settings),
        "upcoming_30_days": _to_default_currency(upcoming_30_days, default_currency, settings),
        "active_count": active_count,
        "category_stats": category_stats,
        "monthly_trend": monthly_trend,
        "currency": default_currency,
    }


def get_calendar_events(user_id: str, year: int, month: int) -> list[dict]:
    """按月生成日历事件（移植 generate_events_for_month）。"""
    subs = db.get_all_subscriptions(user_id)
    events: list[dict] = []
    for sub in subs:
        if not domain.is_calendar_trackable(sub["lifecycle"]):
            continue
        events.extend(_events_for_month(sub, year, month))
    events.sort(key=lambda e: e["date"])
    return events


def _events_for_month(sub: dict, year: int, month: int) -> list[dict]:
    events: list[dict] = []
    if sub["period_type"] == "once":
        due = sub.get("next_due_date")
        if due:
            try:
                d = date.fromisoformat(due)
            except ValueError:
                return events
            if d.year == year and d.month == month:
                _push_event(events, sub, d, domain.calendar_due_event_type(sub["renewal_policy"]))
        return events

    try:
        start_date = date.fromisoformat(sub["start_date"])
    except ValueError:
        return events

    target_start = date(year, month, 1)
    target_end = domain.add_months(target_start, 1) - timedelta(days=1)

    effective_end = None
    if not domain.should_auto_renew_on_wake(sub["auto_renew"], sub["renewal_policy"]):
        if sub.get("next_due_date"):
            try:
                effective_end = date.fromisoformat(sub["next_due_date"])
            except ValueError:
                pass
        else:
            effective_end = domain.add_one_period(
                start_date, sub["period_type"], sub["custom_period_value"], sub["custom_period_unit"]
            )

    current = start_date
    guard = 0
    while current <= target_end:
        guard += 1
        if guard >= 10_000:
            break
        is_within = (current < effective_end) if effective_end else True
        if (is_within and target_start <= current <= target_end
                and current.month == month and current.year == year):
            _push_event(events, sub, current, "cycle_start")
        nxt = domain.add_one_period(
            current, sub["period_type"], sub["custom_period_value"], sub["custom_period_unit"])
        if nxt is None:
            break
        current = nxt

    due = sub.get("next_due_date")
    if due:
        try:
            d = date.fromisoformat(due)
        except ValueError:
            return events
        if d.year == year and d.month == month:
            _push_event(events, sub, d, domain.calendar_due_event_type(sub["renewal_policy"]))
    return events


def _push_event(events: list, sub: dict, d: date, event_type: str) -> None:
    if not domain.is_calendar_event_visible(sub["lifecycle"], sub["updated_at"], d):
        return
    amount = sub["actual_amount"] if sub["actual_amount"] else sub["amount"]
    events.append({
        "date": d.isoformat(),
        "subscription_id": sub["id"],
        "name": sub["name"],
        "amount": amount,
        "amount_formatted": f"{domain.CURRENCY_SYMBOLS.get(sub['currency'], '¥')}{amount / 100:.2f}",
        "currency": sub["currency"],
        "event_type": event_type,
    })
