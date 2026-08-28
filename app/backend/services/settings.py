"""应用设置业务服务：密钥脱敏、更新编排。

对外接口只暴露脱敏视图（``smtp_password_configured`` / ``smtp_password_masked``），
绝不包含密钥原文；更新时通过 SettingsSchema 过滤掩码占位符，保持已有密钥。
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..schemas.settings import SettingsSchema
from ..storage import repositories

_SECRET_SETTING_FIELDS = ("smtp_password", "pushplus_token")


def _mask_secrets(settings: dict) -> dict:
    """返回可通过 HTTP 暴露的设置，绝不包含密钥原文。"""
    public = dict(settings)
    for field in _SECRET_SETTING_FIELDS:
        value = public.pop(field, None)
        configured = bool(value is not None and str(value).strip())
        public[f"{field}_configured"] = configured
        public[f"{field}_masked"] = "*" * len(str(value)) if configured else ""
    return public


def get_public_settings() -> dict:
    return _mask_secrets(repositories.get_app_settings())


def get_raw_settings() -> dict:
    """内部读取（含密钥原文），仅供服务间调用，禁止直接暴露给 HTTP。"""
    return repositories.get_app_settings()


def update_settings(data: Mapping[str, Any]) -> dict:
    updates = SettingsSchema.load(dict(data))
    if not updates:
        return get_public_settings()
    return _mask_secrets(repositories.update_app_settings(updates))
