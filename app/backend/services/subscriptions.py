"""订阅业务服务：Schema 校验 → 业务规则（周期重算、续费策略）→ 仓储编排。

函数签名与旧版 storage/db.py 中对应 CRUD 保持一致，降低迁移成本；
校验逻辑在 schemas/subscription.py，纯持久化在 storage/repositories.py。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

from ..domain import domain
from ..domain.exceptions import ValidationError
from ..schemas.subscription import SubscriptionSchema
from .. import repositories

# 合并校验用的候选字段（更新场景：当前值 + 请求值）
_CANDIDATE_FIELDS = (
    "name",
    "amount",
    "currency",
    "actual_amount",
    "period_type",
    "custom_period_value",
    "custom_period_unit",
    "auto_renew",
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
# 序列化辅助
# --------------------------------------------------------------------------- #


def with_status(sub: dict) -> dict:
    """为订阅附加派生状态（即将到期/已过期等展示字段）。"""
    sub = dict(sub)
    sub["status"] = domain.derive_status(sub.get("lifecycle", "active"), sub.get("next_due_date"))
    sub["status_label"] = domain.STATUS_LABELS.get(sub["status"], sub["status"])
    sub["status_color"] = domain.STATUS_COLORS.get(sub["status"], "#6B7280")
    return sub


def _derive_next_due(normalized: Mapping[str, Any]) -> str | None:
    """按周期推导下次到期日；一次性订阅无后续周期。"""
    if normalized["period_type"] == "once":
        return None
    if normalized.get("next_due_date"):
        return normalized["next_due_date"]
    anchor_start = normalized.get("current_period_start") or normalized["start_date"]
    next_due = domain.add_one_period(
        date.fromisoformat(anchor_start),
        normalized["period_type"],
        normalized.get("custom_period_value"),
        normalized.get("custom_period_unit"),
    )
    return next_due.isoformat() if next_due else None


def _derive_period_and_status(normalized: Mapping[str, Any]) -> dict[str, Any]:
    """自动推导账期字段和生命周期状态。"""
    start_date_str = normalized["start_date"]
    first_pay_str = normalized.get("first_payment_date") or start_date_str
    
    # 1. 周期开始日：未显式传入则默认使用 first_payment_date 或 start_date
    current_period_start = normalized.get("current_period_start") or first_pay_str
    
    # 2. 下次到期日
    next_due = _derive_next_due(normalized)
    
    # 3. 周期结束日：未显式传入时等于下次到期日；若无到期日（如一次性），等于开始日
    current_period_end = normalized.get("current_period_end") or next_due or current_period_start
    
    # 4. 最后付款日：未显式传入则默认使用首次付款日
    last_payment_date = normalized.get("last_payment_date") or first_pay_str
    
    # 5. 自动续费/手动续费确认状态：由单一事实来源 renewal_policy 判定
    renewal_confirmed = normalized.get("renewal_confirmed")
    if renewal_confirmed is None:
        policy = normalized.get("renewal_policy") or ("auto" if normalized.get("auto_renew") else "manual")
        renewal_confirmed = 1 if policy == "auto" else 0
    else:
        renewal_confirmed = int(renewal_confirmed)
        
    return {
        "current_period_start": current_period_start,
        "current_period_end": current_period_end,
        "next_due_date": next_due,
        "last_payment_date": last_payment_date,
        "renewal_confirmed": renewal_confirmed,
    }


def _build_full_row(user_id: str, normalized: Mapping[str, Any]) -> dict:
    """Schema 归一化字段 → 全列落库字典（id/时间戳/周期与状态推导）。"""
    timestamp = repositories.now_utc()
    derived = _derive_period_and_status(normalized)
    return {
        "id": repositories.new_id(),
        "user_id": str(user_id or "local"),
        "name": normalized["name"],
        "amount": normalized["amount"],
        "currency": normalized["currency"],
        "actual_amount": normalized.get("actual_amount"),
        "category_id": normalized.get("category_id"),
        "notes": normalized.get("notes"),
        "period_type": normalized["period_type"],
        "custom_period_value": normalized.get("custom_period_value"),
        "custom_period_unit": normalized.get("custom_period_unit"),
        "auto_renew": int(normalized.get("renewal_policy") == "auto"),
        "sharing_role": normalized.get("sharing_role"),
        "sharing_count": normalized.get("sharing_count"),
        "start_date": normalized["start_date"],
        "first_payment_date": normalized.get("first_payment_date"),
        "current_period_start": derived["current_period_start"],
        "current_period_end": derived["current_period_end"],
        "next_due_date": derived["next_due_date"],
        "next_billing_date": normalized.get("next_billing_date"),
        "last_payment_date": derived["last_payment_date"],
        "renewal_confirmed": derived["renewal_confirmed"],
        "lifecycle": normalized["lifecycle"],
        "renewal_policy": normalized["renewal_policy"],
        "billing_status": normalized["billing_status"],
        "grace_period_ends_at": normalized.get("grace_period_ends_at"),
        "cancelled_at": normalized.get("cancelled_at"),
        "paused_at": normalized.get("paused_at"),
        "deleted_at": None,
        "sync_version": 1,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #


def list_subscriptions(user_id: str) -> list[dict]:
    return repositories.get_all_subscriptions(user_id)


def list_subscriptions_paginated(
    user_id: str,
    page: int = 1,
    per_page: int = 20,
    lifecycle: str | None = None,
    category_id: str | None = None,
) -> dict:
    """分页查询订阅列表，返回包含分页信息的字典。"""
    from math import ceil

    items, total = repositories.get_subscriptions_paginated(
        user_id=user_id,
        page=page,
        per_page=per_page,
        lifecycle=lifecycle,
        category_id=category_id,
    )
    return {
        'items': [with_status(s) for s in items],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': ceil(total / per_page) if total > 0 else 0,
    }


def get_subscription(sub_id: str, user_id: str) -> dict | None:
    return repositories.get_subscription_by_id(sub_id, user_id)


def create_subscription(user_id: str, data: dict) -> dict:
    normalized = SubscriptionSchema.validate_create(data)
    row_data = _build_full_row(user_id, normalized)
    created = repositories.insert_subscription(row_data)

    # 自动创建首笔支付流水（如果存在有效的付款日/开始日）
    first_pay = created.get("first_payment_date") or created.get("start_date")
    if first_pay:
        p_start = created.get("current_period_start") or created.get("start_date")
        p_end = created.get("current_period_end") or created.get("next_due_date") or created.get("start_date")
        repositories.create_payment_for_subscription(
            subscription_id=created["id"],
            user_id=user_id,
            amount=created["amount"],
            currency=created["currency"],
            paid_at=first_pay,
            period_start=p_start,
            period_end=p_end,
            payment_type="first",
            note=f"初始支付 {created['name']}",
        )
    return created


def update_subscription(sub_id: str, user_id: str, data: dict) -> dict | None:
    current = repositories.get_subscription_by_id(sub_id, user_id)
    if current is None:
        return None
    requested = {field for field in repositories.SUBSCRIPTION_FIELDS if field in data}
    if not requested:
        return current
    updates = _compute_updates(current, data, requested)
    if not updates:
        return current
    return repositories.update_subscription_fields(sub_id, user_id, updates)


def delete_subscription(sub_id: str, user_id: str, hard: bool = False) -> bool:
    return repositories.delete_subscription(sub_id, user_id, hard=hard)


def restore_subscription(sub_id: str, user_id: str) -> dict | None:
    return repositories.restore_subscription(sub_id, user_id)


def renew_subscription(sub_id: str, user_id: str) -> dict | None:
    """续费：把 next_due_date 推进到下一期（一次性订阅不支持）。"""
    current = repositories.get_subscription_by_id(sub_id, user_id)
    if current is None or current["period_type"] == "once":
        return None
    due = date.fromisoformat(current["next_due_date"] or current["start_date"])
    start = date.fromisoformat(current["start_date"])
    next_due = domain.add_one_period(
        due,
        current["period_type"],
        current["custom_period_value"],
        current["custom_period_unit"],
        anchor_day=domain.billing_anchor_day(start),
    )
    if next_due is None:
        return None
    
    # 更新订阅状态
    updated = repositories.renew_subscription(sub_id, user_id, next_due.isoformat())
    if updated:
        today_str = date.today().isoformat()
        period_start = current["current_period_end"] or current["start_date"]
        # 创建支付流水
        repositories.create_payment_for_subscription(
            subscription_id=sub_id,
            user_id=user_id,
            amount=current["amount"],
            currency=current["currency"],
            paid_at=today_str,
            period_start=period_start,
            period_end=next_due.isoformat(),
            payment_type="renewal",
            note=f"续费 {current['name']}"
        )
        # 更新订阅的最后付款日期及当前账期
        repositories.update_subscription_fields(sub_id, user_id, {
            "last_payment_date": today_str,
            "current_period_start": period_start,
            "current_period_end": next_due.isoformat(),
        })
    return updated


# --------------------------------------------------------------------------- #
# 更新计算（旧版 _normalize_update_subscription 的等价实现）
# --------------------------------------------------------------------------- #


def _compute_updates(
    current: Mapping[str, Any], data: Mapping[str, Any], requested: set[str]
) -> dict[str, Any]:
    schema = SubscriptionSchema.validate_update(dict(data))

    # 合并当前值 + 请求值 → 全量校验（与旧版 candidate 语义一致）
    candidate: dict[str, Any] = {field: current.get(field) for field in _CANDIDATE_FIELDS}
    for field in schema:
        if field in _CANDIDATE_FIELDS:
            candidate[field] = schema[field]

    effective_period = domain.normalize_period_type(candidate.get("period_type"))
    update_auto = schema.get("auto_renew") if "auto_renew" in requested else None
    update_policy = schema.get("renewal_policy") if "renewal_policy" in requested else None
    effective_auto, effective_policy = domain.resolve_renewal_on_update(
        bool(current.get("auto_renew")),
        str(current.get("renewal_policy") or "manual"),
        update_auto,
        update_policy,
        period_type=effective_period,
    )
    candidate["auto_renew"] = effective_auto
    candidate["renewal_policy"] = effective_policy

    if effective_period != "custom":
        if any(
            field in data and data[field] not in (None, "")
            for field in ("custom_period_value", "custom_period_unit")
        ):
            raise ValidationError("custom_period_value/custom_period_unit仅适用于custom周期")
        candidate["custom_period_value"] = None
        candidate["custom_period_unit"] = None

    normalized = domain.normalize_subscription_data(candidate)

    updates: dict[str, Any] = {}
    for field in requested:
        if field in normalized:
            updates[field] = normalized[field]
        elif field in schema:  # notes / category_id / sharing_*（Schema 已清洗）
            updates[field] = schema[field]

    period_changed = normalized["period_type"] != current.get("period_type")
    custom_changed = any(
        field in data for field in ("period_type", "custom_period_value", "custom_period_unit")
    )
    if period_changed or custom_changed:
        updates["period_type"] = normalized["period_type"]
        updates["custom_period_value"] = normalized["custom_period_value"]
        updates["custom_period_unit"] = normalized["custom_period_unit"]

    if "auto_renew" in data or "renewal_policy" in data or period_changed:
        updates["auto_renew"] = int(normalized.get("renewal_policy") == "auto")
        updates["renewal_policy"] = normalized["renewal_policy"]

    explicit_next_due = "next_due_date" in data
    if normalized["period_type"] == "once":
        updates["next_due_date"] = None
        updates["current_period_end"] = updates.get("current_period_start") or current.get("current_period_start")
    elif (period_changed or custom_changed or "start_date" in data) and (
        not explicit_next_due or data.get("next_due_date") in (None, "")
    ):
        derived_due = _derive_next_due(normalized)
        updates["next_due_date"] = derived_due
        if "current_period_end" not in data:
            updates["current_period_end"] = derived_due

    return updates


# --------------------------------------------------------------------------- #
# 备份/导入导出辅助（全量读取与原始行写入）
# --------------------------------------------------------------------------- #


def get_all_subscriptions_raw(user_id: str | None = None) -> list[dict]:
    return repositories.get_all_subscriptions_raw(user_id)


def get_subscription_dedup_keys(user_id: str | None = None) -> set:
    return repositories.get_subscription_dedup_keys(user_id)


def insert_subscription_raw(sub: Mapping[str, Any], user_id: str | None = None) -> dict:
    """安全插入外部订阅行（调用方需传入已归一化的全列字典）。"""
    return repositories.insert_subscription_raw(sub)


def replace_subscription_raw(sub: Mapping[str, Any], user_id: str | None = None) -> bool:
    """按 owner 安全替换订阅行，不允许跨用户覆盖。"""
    return repositories.replace_subscription_raw(sub)
