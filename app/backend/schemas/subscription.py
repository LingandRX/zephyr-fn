"""订阅参数校验 Schema。

覆盖三种场景：
- validate_create  : 创建（必填字段 + 严格校验 + 默认值）
- validate_update  : 更新（仅归一化请求中出现的字段，允许部分更新）
- validate_raw     : 外部原始行（导入/合并），字段完整或带默认值

跨字段业务规则（续费策略解析、下次到期日重算、custom 周期互斥）在
services/subscriptions 中处理。所有校验失败统一抛 ValidationError。
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any, Callable

from ..core import domain
from ..core.exceptions import ValidationError
from .base import MAX_NOTES_LENGTH, optional_text, reject_explicit_blank, require_mapping

# 创建场景必填字段
_REQUIRED_FIELDS = ("name", "amount", "currency", "period_type", "auto_renew",
                    "start_date", "lifecycle")
# 更新场景必填（不允许清空）字段
_REQUIRED_ON_UPDATE = ("name", "amount", "currency", "period_type", "auto_renew",
                       "lifecycle", "renewal_policy", "start_date")

# 由 Schema 校验并归一化的领域字段
_DOMAIN_FIELDS = (
    "name", "amount", "currency", "actual_amount", "period_type",
    "custom_period_value", "custom_period_unit", "auto_renew", "start_date",
    "first_payment_date", "next_due_date", "lifecycle", "renewal_policy",
    "billing_status", "grace_period_ends_at",
)
# 由 Schema 清洗的持久化字段
_CLEAN_FIELDS = ("category_id", "notes", "sharing_role", "sharing_count")

_CREATE_DEFAULTS = {
    "amount": 0,
    "currency": "CNY",
    "period_type": "month",
    "auto_renew": True,
    "lifecycle": "active",
    "billing_status": "normal",
    "start_date": date.today().isoformat(),
}


def _normalize_name(value: Any) -> str:
    name = str(value or "").strip()
    if not name:
        raise ValidationError("名称不能为空")
    if len(name) > domain.MAX_SUBSCRIPTION_NAME_LENGTH:
        raise ValidationError(f"名称不能超过{domain.MAX_SUBSCRIPTION_NAME_LENGTH}字")
    return name


def _normalize_custom_unit(value: Any) -> str | None:
    if value in (None, ""):
        return None
    unit = str(value).strip()
    if unit not in domain.CUSTOM_UNITS:
        raise ValidationError(f"自定义周期单位值无效: {value}")
    return unit


# 部分更新场景的字段级归一化器
_FIELD_NORMALIZERS: dict[str, Callable[[Any], Any]] = {
    "name": _normalize_name,
    "amount": lambda v: domain.normalize_non_negative_int(v, "金额", default=0),
    "currency": lambda v: domain.normalize_currency(v, default="CNY"),
    "actual_amount": lambda v: domain.normalize_non_negative_int(
        v, "实际金额", allow_none=True),
    "period_type": lambda v: domain.normalize_period_type(v, default="month"),
    "custom_period_value": lambda v: (
        domain.normalize_positive_int(v, "自定义周期值") if v not in (None, "") else None),
    "custom_period_unit": _normalize_custom_unit,
    "auto_renew": lambda v: domain.normalize_bool(v, "自动续费", default=True),
    "start_date": lambda v: domain.normalize_date(v, "开始日期", allow_none=False),
    "first_payment_date": lambda v: domain.normalize_date(v, "首次付款日"),
    "next_due_date": lambda v: domain.normalize_date(v, "下次到期日"),
    "lifecycle": lambda v: domain.normalize_lifecycle(v, default="active"),
    "renewal_policy": lambda v: domain.normalize_renewal_policy(v, default=None),
    "billing_status": lambda v: domain.normalize_billing_status(v, default="normal"),
    "grace_period_ends_at": lambda v: domain.normalize_date(v, "宽限期结束日期"),
}


def _as_validation_error(fn: Callable[[Any], Any], value: Any) -> Any:
    """领域函数抛 ValueError 时统一转译 ValidationError（消息不变）。"""
    try:
        return fn(value)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc


class SubscriptionSchema:
    """订阅参数校验：包装 core/domain 严格校验，产出归一化业务字段。"""

    @classmethod
    def validate_create(cls, data: Any) -> dict:
        """创建场景：返回可落库的业务字段（含清洗后的 category/notes/sharing）。"""
        payload = require_mapping(data)
        reject_explicit_blank(payload, _REQUIRED_FIELDS)
        try:
            normalized = domain.normalize_subscription_data(
                payload, defaults=_CREATE_DEFAULTS)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        return cls._build(payload, normalized)

    @classmethod
    def validate_update(cls, data: Any) -> dict:
        """更新场景：仅归一化请求中出现的字段。"""
        payload = require_mapping(data)
        reject_explicit_blank(payload, _REQUIRED_ON_UPDATE)
        requested = {
            field for field in _DOMAIN_FIELDS + _CLEAN_FIELDS
            if field in payload
        }
        if not requested:
            return {}
        normalized: dict[str, Any] = {}
        for field in _DOMAIN_FIELDS:
            if field in requested:
                normalized[field] = _as_validation_error(
                    _FIELD_NORMALIZERS[field], payload[field])
        return cls._build(payload, normalized, only_requested=requested)

    @classmethod
    def validate_raw(cls, sub: Any, user_id: str | None = None) -> dict:
        """外部原始行（JSON/CSV/DB 备份导入）校验归一化。"""
        if not isinstance(sub, Mapping):
            raise ValidationError("订阅数据必须是对象")
        payload = dict(sub)
        reject_explicit_blank(payload, _REQUIRED_FIELDS)
        try:
            normalized = domain.normalize_subscription_data(
                payload, defaults=_CREATE_DEFAULTS)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        if "user_id" not in payload or not str(payload.get("user_id") or "").strip():
            payload["user_id"] = user_id or "local"
        return cls._build(payload, normalized)

    @staticmethod
    def _build(payload: Mapping[str, Any], normalized: dict,
               only_requested: set[str] | None = None) -> dict:
        """组装 Schema 输出：领域归一化字段 + 清洗后的持久化字段。"""
        result: dict[str, Any] = {
            field: normalized.get(field)
            for field in _DOMAIN_FIELDS
            if only_requested is None or field in only_requested
        }
        cleaned = {
            "category_id": optional_text(payload.get("category_id")),
            "notes": optional_text(payload.get("notes"), "备注", MAX_NOTES_LENGTH),
            "sharing_role": optional_text(payload.get("sharing_role")),
            "sharing_count": domain.normalize_non_negative_int(
                payload.get("sharing_count"), "共享人数", allow_none=True
            ) if payload.get("sharing_count") not in (None, "") else None,
        }
        for field in _CLEAN_FIELDS:
            if only_requested is None or field in only_requested:
                result[field] = cleaned[field]
        return result
