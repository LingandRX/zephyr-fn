"""应用设置参数校验 Schema。

职责：
- 过滤请求中的掩码密钥占位符（保持已有密钥不变）；
- 处理 ``{field}_clear`` 显式清空标记；
- 按字段类型做严格转换（汇率 float、开关 bool、端口 int 等）。

密钥脱敏（对外只暴露 *_configured / *_masked）在 services/settings 完成。
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..core.exceptions import ValidationError
from ..storage.repositories import SETTINGS_FIELDS, is_secret_placeholder

_SECRET_FIELDS = ("smtp_password", "pushplus_token", "pushplus_smtp_password")
_INT_FIELDS = ("notification_days", "smtp_port", "pushplus_smtp_port")
_FLOAT_FIELDS = ("exchange_rate_usd", "exchange_rate_hkd")
_BOOL_FIELDS = ("auto_start", "tray_mode", "email_enabled",
                "notification_enabled", "pushplus_enabled")


class SettingsSchema:
    """设置更新校验：返回可直接落库的字段字典（不含占位符）。"""

    @classmethod
    def load(cls, data: Mapping[str, Any]) -> dict:
        if not isinstance(data, Mapping):
            raise ValidationError("请求数据必须是对象")

        updates: dict[str, Any] = {}
        cleared_fields = {
            field for field in _SECRET_FIELDS
            if data.get(f"{field}_clear")
        }
        for field in cleared_fields:
            updates[field] = None

        for field in SETTINGS_FIELDS:
            if field not in data or field in cleared_fields:
                continue
            value = data[field]
            if field in _SECRET_FIELDS:
                if is_secret_placeholder(value):
                    continue
                updates[field] = str(value) if value else None
            elif field in _FLOAT_FIELDS:
                try:
                    updates[field] = float(value)
                except (TypeError, ValueError):
                    continue
            elif field in _INT_FIELDS:
                updates[field] = cls._to_int(value)
            elif field in _BOOL_FIELDS:
                updates[field] = int(cls._to_bool(value))
            else:
                updates[field] = str(value) if value not in (None, "") else None

        # 请求中出现的 *_configured 输出字段不允许回写
        for key in list(updates):
            if key.endswith("_configured"):
                updates.pop(key, None)
        return updates

    @staticmethod
    def _to_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None if value in (None, "") else 0

    @staticmethod
    def _to_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        return str(value).lower() in ("1", "true", "yes", "on")
