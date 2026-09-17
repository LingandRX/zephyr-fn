"""邮件通知模板定义与渲染引擎。

仅保留极简文本模板（minimal）：纯文字精炼通知，轻量低干扰，适合各类邮件客户端及移动设备。
支持真实订阅提醒渲染与测试邮件渲染。
"""

from __future__ import annotations

import html
from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any

from ...domain import domain

TEMPLATE_OPTIONS = [
    {"id": "minimal", "name": "极简文本", "description": "纯文字精简通知，轻量低干扰"},
]

VALID_TEMPLATE_IDS = frozenset(t["id"] for t in TEMPLATE_OPTIONS)


def _safe_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


def _format_amount(amount_cents: Any, currency: str) -> str:
    curr = _safe_str(currency).upper() or "CNY"
    sym = domain.CURRENCY_SYMBOLS.get(curr, "¥")
    try:
        val = int(amount_cents or 0) / 100.0
        return f"{sym}{val:.2f}"
    except (TypeError, ValueError):
        return f"{sym}0.00"


def _format_period(period_type: str | None, value: Any = None, unit: str | None = None) -> str:
    p = _safe_str(period_type)
    if p == "custom" and value and unit:
        unit_map = {"day": "天", "week": "周", "month": "月", "year": "年"}
        return f"每 {value} {unit_map.get(str(unit), str(unit))}"
    return domain.PERIOD_LABELS.get(p, "月付")


def _format_renewal_policy(policy: str | None, auto_renew: Any = None) -> str:
    p = _safe_str(policy)
    policy_map = {
        "auto": "自动续费",
        "manual": "手动续费",
        "stop": "到期停止",
        "stop_on_expiry": "到期后停止",
    }
    if p in policy_map:
        return policy_map[p]
    if auto_renew:
        return "自动续费"
    return "手动续费"


def _extract_sub_data(sub: Mapping[str, Any] | None, is_test: bool = False) -> dict[str, Any]:
    today = date.today()
    if is_test or not sub:
        due_date = today + timedelta(days=3)
        return {
            "name": sub.get("name") if sub else "Netflix 标准会员",
            "amount_str": _format_amount(
                sub.get("amount") if sub else 2800, sub.get("currency") if sub else "CNY"
            ),
            "currency": sub.get("currency") if sub else "CNY",
            "due_date_str": sub.get("next_due_date") if sub else due_date.isoformat(),
            "days_until": 3,
            "category": sub.get("category_name") or sub.get("category") if sub else "流媒体",
            "period": _format_period(sub.get("period_type") if sub else "month"),
            "renewal_policy": _format_renewal_policy(sub.get("renewal_policy") if sub else "auto"),
            "notes": sub.get("notes") if sub else "4K 超清家庭套餐",
            "is_test": True,
        }

    # 实际订阅
    due_raw = _safe_str(sub.get("next_due_date"))
    if len(due_raw) > 10 and due_raw[10] in ("T", " "):
        due_raw = due_raw[:10]
    try:
        due_date = date.fromisoformat(due_raw)
    except (TypeError, ValueError):
        due_date = today

    days_until = max(0, (due_date - today).days)
    amount_str = _format_amount(sub.get("amount"), _safe_str(sub.get("currency")))
    name = _safe_str(sub.get("name")) or "未命名订阅"
    category = _safe_str(sub.get("category_name") or sub.get("category")) or "未分类"
    period = _format_period(
        sub.get("period_type"), sub.get("custom_period_value"), sub.get("custom_period_unit")
    )
    renewal_policy = _format_renewal_policy(sub.get("renewal_policy"), sub.get("auto_renew"))
    notes = _safe_str(sub.get("notes"))

    return {
        "name": name,
        "amount_str": amount_str,
        "currency": _safe_str(sub.get("currency")).upper() or "CNY",
        "due_date_str": due_date.isoformat(),
        "days_until": days_until,
        "category": category,
        "period": period,
        "renewal_policy": renewal_policy,
        "notes": notes,
        "is_test": False,
    }


# ========================================================================= #
# 模板: minimal (极简文本)
# ========================================================================= #


def _render_minimal(data: dict[str, Any]) -> tuple[str, str, str]:
    name = data["name"]
    amount = data["amount_str"]
    due_date = data["due_date_str"]
    days = data["days_until"]
    period = data["period"]
    is_test = data["is_test"]

    if is_test:
        subject = f"【订阅管理】邮件通知测试 (极简文本) - {name}"
        text_body = (
            f"【邮件通知测试】\n"
            f"服务: {name}\n"
            f"金额: {amount} / {period}\n"
            f"测试时间: {date.today().isoformat()}\n"
            f"SMTP 配置工作正常。\n"
            f"--- Zephyr 订阅管理"
        )
    elif days == 0:
        subject = f"【到期】{name} 今日到期 ({amount})"
        text_body = (
            f"【订阅到期提醒】{name}\n"
            f"今日到期扣费：{amount}（{period}）\n"
            f"扣款日期：{due_date}\n"
            f"如无需续费，请及时前往服务提供商取消。\n"
            f"--- Zephyr 订阅管理"
        )
    else:
        subject = f"【到期】{name} 将在 {days} 天后到期 ({amount})"
        text_body = (
            f"【订阅到期提醒】{name}\n"
            f"将在 {days} 天后到期扣费：{amount}（{period}）\n"
            f"扣款日期：{due_date}\n"
            f"如无需续费，请及时前往服务提供商取消。\n"
            f"--- Zephyr 订阅管理"
        )

    # 极简模式下的 HTML 为保持极简特性的纯净排版
    e_text = html.escape(text_body).replace("\n", "<br>")
    html_body = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"></head>
<body style="margin:20px;font-family:monospace,sans-serif;font-size:14px;color:#1e293b;line-height:1.7;background:#ffffff;">
  <div style="padding:16px 20px;border-left:3px solid #6366f1;background:#f8fafc;max-width:480px;">
    {e_text}
  </div>
</body>
</html>
"""
    return subject, text_body, html_body


# ========================================================================= #
# 统一对外渲染入口
# ========================================================================= #


def render_email_template(
    template_id: str | None = None,
    sub: Mapping[str, Any] | None = None,
    is_test: bool = False,
) -> tuple[str, str, str | None]:
    """根据模板 ID 渲染邮件通知内容。

    当前系统统一采用「极简文本」通知风格。

    Args:
        template_id: 模板标识（保留参数以兼容旧接口，统一以极简文本渲染）
        sub: 订阅数据字典（is_test 为 True 时可为空）
        is_test: 是否为测试邮件

    Returns:
        tuple[str, str, str | None]: (邮件主题, 纯文本正文, HTML 正文或 None)
    """
    data = _extract_sub_data(sub, is_test=is_test)
    return _render_minimal(data)
