"""通知服务：免打扰判断、筛选需要通知的订阅、生成通知文案（移植 zephyr-tarui）。"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import db
import domain


def is_do_not_disturb() -> bool:
    settings = db.get_app_settings()
    start = settings.get("do_not_disturb_start")
    end = settings.get("do_not_disturb_end")
    if not start or not end:
        return False
    try:
        now_hour = datetime.now().hour
        start_hour = int(start.split(":")[0])
        end_hour = int(end.split(":")[0])
    except (ValueError, AttributeError):
        return False
    if start_hour <= end_hour:
        return start_hour <= now_hour < end_hour
    return now_hour >= start_hour or now_hour < end_hour


def get_subscriptions_needing_notification(user_id: str | None = None) -> list[dict]:
    settings = db.get_app_settings()
    reminder_days = max(0, int(settings.get("notification_days") or 3))
    today = date.today()
    end_date = today + timedelta(days=reminder_days)

    subs = db.get_all_subscriptions(user_id) if user_id else db.get_all_subscriptions_raw()
    result = []
    for sub in subs:
        if sub["lifecycle"] != "active":
            continue
        due = sub.get("next_due_date")
        if not due:
            continue
        try:
            d = date.fromisoformat(due)
        except ValueError:
            continue
        if today <= d <= end_date:
            result.append(sub)
    return result


def generate_notification_content(sub: dict) -> tuple[str, str]:
    today = date.today()
    due_date = sub["next_due_date"]
    days_until = (date.fromisoformat(due_date) - today).days
    symbol = domain.CURRENCY_SYMBOLS.get(sub["currency"], "¥")
    amount = f"{symbol}{sub['amount'] / 100:.2f}"

    title = f"{sub['name']} 今天到期" if days_until == 0 else f"{sub['name']} 将在 {days_until} 天后到期"
    body = f"金额: {amount}  到期日: {due_date}"
    return title, body
