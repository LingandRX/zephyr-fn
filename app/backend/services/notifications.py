"""通知服务：免打扰判断、到期筛选、文案以及通知幂等领取。

幂等领取（claim_notification / complete_notification）委托给
storage/repositories 的原子 UPSERT 实现；本模块保留业务算法与兼容入口。
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from ..core import domain
from ..storage import repositories

# 兼容入口：调度器与外部调用方继续使用这些名字
claim_notification = repositories.claim_notification
complete_notification = repositories.complete_notification
has_channel_notified_today = repositories.has_channel_notified_today
log_notification = repositories.log_notification

LOGGER_NAME = "subscription"
NOTIFICATION_CLAIM_TTL_SECONDS = 6 * 60 * 60


def _logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def _parse_clock(value: Any) -> int | None:
    """把 HH:MM 转成当天分钟数；非法配置返回 None。"""
    if value in (None, ""):
        return None
    text = str(value).strip()
    parts = text.split(":")
    if len(parts) != 2:
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except (TypeError, ValueError):
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour * 60 + minute


def is_do_not_disturb(settings: dict | None = None,
                      now: datetime | None = None) -> bool:
    """判断当前时间是否处于免打扰区间，精确到分钟并支持跨午夜。"""
    settings = settings if settings is not None else repositories.get_app_settings()
    start = _parse_clock(settings.get("do_not_disturb_start"))
    end = _parse_clock(settings.get("do_not_disturb_end"))
    if start is None or end is None or start == end:
        return False

    current = now or datetime.now()
    current_minutes = current.hour * 60 + current.minute
    if start < end:
        return start <= current_minutes < end
    return current_minutes >= start or current_minutes < end


def _reminder_days(settings: dict, override: int | None) -> int:
    value: Any = override if override is not None else settings.get("notification_days")
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        if override is not None:
            try:
                return max(0, int(settings.get("notification_days") or 7))
            except (TypeError, ValueError):
                return 7
        return 7


def get_subscriptions_needing_notification(
    user_id: str | None = None, reminder_days: int | None = None
) -> list[dict]:
    """返回提醒窗口内的订阅。"""
    settings = repositories.get_app_settings()
    days = _reminder_days(settings, reminder_days)
    today = date.today()
    end_date = today + timedelta(days=days)

    if user_id is None:
        subs = repositories.get_all_subscriptions_raw()
    else:
        user = str(user_id).strip()
        if not user:
            return []
        subs = repositories.get_all_subscriptions(user)

    result = []
    for sub in subs:
        if sub.get("lifecycle") != "active":
            continue
        due = sub.get("next_due_date")
        if not due:
            continue
        try:
            due_text = str(due)
            if len(due_text) > 10 and due_text[10] in ("T", " "):
                due_text = due_text[:10]
            due_date = date.fromisoformat(due_text)
        except (TypeError, ValueError):
            continue
        if today <= due_date <= end_date:
            result.append(sub)
    result.sort(key=lambda item: (item.get("next_due_date") or "", item.get("name") or ""))
    return result


def generate_notification_content(sub: dict) -> tuple[str, str]:
    today = date.today()
    due_date = sub.get("next_due_date")
    if not due_date:
        raise ValueError("订阅缺少下次到期日")
    try:
        due_date = str(due_date)
        if len(due_date) > 10 and due_date[10] in ("T", " "):
            due_date = due_date[:10]
        due = date.fromisoformat(due_date)
    except (TypeError, ValueError) as exc:
        raise ValueError("下次到期日格式无效") from exc

    days_until = (due - today).days
    currency = str(sub.get("currency") or "CNY").upper()
    symbol = domain.CURRENCY_SYMBOLS.get(currency, "¥")
    try:
        amount = f"{symbol}{int(sub.get('amount') or 0) / 100:.2f}"
    except (TypeError, ValueError) as exc:
        raise ValueError("订阅金额格式无效") from exc

    name = str(sub.get("name") or "未命名订阅")
    title = f"{name} 今天到期" if days_until == 0 else f"{name} 将在 {days_until} 天后到期"
    body = f"金额: {amount}  到期日: {due.isoformat()}"
    return title, body


def get_upcoming_notifications(user_id: str) -> list[dict]:
    """返回用户提醒窗口内的到期通知列表（含文案），按剩余天数升序。"""
    settings = repositories.get_app_settings()
    reminder_days = max(0, int(settings.get("notification_days") or 7))
    today = date.today()
    end = today + timedelta(days=reminder_days)
    result = []
    for sub in repositories.get_all_subscriptions(user_id):
        if sub["lifecycle"] != "active" or not sub.get("next_due_date"):
            continue
        try:
            due = date.fromisoformat(sub["next_due_date"])
        except ValueError:
            continue
        if today <= due <= end:
            title, body = generate_notification_content(sub)
            result.append({
                "id": sub["id"],
                "name": sub["name"],
                "due_date": sub["next_due_date"],
                "days_until": (due - today).days,
                "amount": sub["amount"],
                "currency": sub["currency"],
                "title": title,
                "body": body,
            })
    result.sort(key=lambda item: item["days_until"])
    return result


# 兼容别名
finish_notification = complete_notification
