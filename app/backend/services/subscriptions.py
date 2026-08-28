"""订阅业务服务：Schema 校验 → 业务规则（周期重算、续费策略）→ 仓储编排。

函数签名与旧版 storage/db.py 中对应 CRUD 保持一致，降低迁移成本；
校验逻辑在 schemas/subscription.py，纯持久化在 storage/repositories.py。
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

from ..core import domain
from ..core.exceptions import ValidationError
from ..schemas.subscription import SubscriptionSchema
from ..storage import repositories

# 合并校验用的候选字段（更新场景：当前值 + 请求值）
_CANDIDATE_FIELDS = (
    "name", "amount", "currency", "actual_amount", "period_type",
    "custom_period_value", "custom_period_unit", "auto_renew", "start_date",
    "first_payment_date", "next_due_date", "lifecycle", "renewal_policy",
    "billing_status", "grace_period_ends_at",
)


# --------------------------------------------------------------------------- #
# 序列化辅助
# --------------------------------------------------------------------------- #

def with_status(sub: dict) -> dict:
    """为订阅附加派生状态（即将到期/已过期等展示字段）。"""
    sub = dict(sub)
    sub["status"] = domain.derive_status(sub.get("lifecycle", "active"),
                                         sub.get("next_due_date"))
    sub["status_label"] = domain.STATUS_LABELS.get(sub["status"], sub["status"])
    sub["status_color"] = domain.STATUS_COLORS.get(sub["status"], "#6B7280")
    return sub


def _derive_next_due(normalized: Mapping[str, Any]) -> str | None:
    """按周期推导下次到期日；一次性订阅无后续周期。"""
    if normalized["period_type"] == "once":
        return None
    if normalized.get("next_due_date"):
        return normalized["next_due_date"]
    next_due = domain.add_one_period(
        date.fromisoformat(normalized["start_date"]),
        normalized["period_type"],
        normalized.get("custom_period_value"),
        normalized.get("custom_period_unit"),
    )
    return next_due.isoformat() if next_due else None


def _build_full_row(user_id: str, normalized: Mapping[str, Any]) -> dict:
    """Schema 归一化字段 → 全列落库字典（id/时间戳/周期推导）。"""
    timestamp = repositories.now_utc()
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
        "auto_renew": int(normalized["auto_renew"]),
        "sharing_role": normalized.get("sharing_role"),
        "sharing_count": normalized.get("sharing_count"),
        "start_date": normalized["start_date"],
        "first_payment_date": normalized.get("first_payment_date"),
        "next_due_date": _derive_next_due(normalized),
        "lifecycle": normalized["lifecycle"],
        "renewal_policy": normalized["renewal_policy"],
        "billing_status": normalized["billing_status"],
        "grace_period_ends_at": normalized.get("grace_period_ends_at"),
        "sync_version": 1,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #

def list_subscriptions(user_id: str) -> list[dict]:
    return repositories.get_all_subscriptions(user_id)


def get_subscription(sub_id: str, user_id: str) -> dict | None:
    return repositories.get_subscription_by_id(sub_id, user_id)


def create_subscription(user_id: str, data: dict) -> dict:
    normalized = SubscriptionSchema.validate_create(data)
    return repositories.insert_subscription(_build_full_row(user_id, normalized))


def update_subscription(sub_id: str, user_id: str, data: dict) -> dict | None:
    current = repositories.get_subscription_by_id(sub_id, user_id)
    if current is None:
        return None
    requested = {
        field for field in repositories.SUBSCRIPTION_FIELDS
        if field in data
    }
    if not requested:
        return current
    updates = _compute_updates(current, data, requested)
    if not updates:
        return current
    return repositories.update_subscription_fields(sub_id, user_id, updates)


def delete_subscription(sub_id: str, user_id: str) -> bool:
    return repositories.delete_subscription(sub_id, user_id)


def renew_subscription(sub_id: str, user_id: str) -> dict | None:
    """续费：把 next_due_date 推进到下一期（一次性订阅不支持）。"""
    current = repositories.get_subscription_by_id(sub_id, user_id)
    if current is None or current["period_type"] == "once":
        return None
    due = date.fromisoformat(current["next_due_date"] or current["start_date"])
    next_due = domain.add_one_period(
        due, current["period_type"], current["custom_period_value"],
        current["custom_period_unit"],
    )
    if next_due is None:
        return None
    return repositories.renew_subscription(sub_id, user_id, next_due.isoformat())


# --------------------------------------------------------------------------- #
# 更新计算（旧版 _normalize_update_subscription 的等价实现）
# --------------------------------------------------------------------------- #

def _compute_updates(current: Mapping[str, Any], data: Mapping[str, Any],
                     requested: set[str]) -> dict[str, Any]:
    schema = SubscriptionSchema.validate_update(dict(data))

    # 合并当前值 + 请求值 → 全量校验（与旧版 candidate 语义一致）
    candidate: dict[str, Any] = {
        field: current.get(field) for field in _CANDIDATE_FIELDS
    }
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
            raise ValidationError(
                "custom_period_value/custom_period_unit仅适用于custom周期")
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
        field in data
        for field in ("period_type", "custom_period_value", "custom_period_unit")
    )
    if period_changed or custom_changed:
        updates["period_type"] = normalized["period_type"]
        updates["custom_period_value"] = normalized["custom_period_value"]
        updates["custom_period_unit"] = normalized["custom_period_unit"]

    if "auto_renew" in data or "renewal_policy" in data or period_changed:
        updates["auto_renew"] = int(normalized["auto_renew"])
        updates["renewal_policy"] = normalized["renewal_policy"]

    explicit_next_due = "next_due_date" in data
    if normalized["period_type"] == "once":
        updates["next_due_date"] = None
    elif (
        (period_changed or custom_changed or "start_date" in data)
        and (not explicit_next_due or data.get("next_due_date") in (None, ""))
    ):
        updates["next_due_date"] = _derive_next_due(normalized)

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
