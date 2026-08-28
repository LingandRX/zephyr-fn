"""Schema/Serializer 层：请求参数校验与归一化。

设计约定：
- Schema 只做「输入 → 归一化字段」的纯校验，不做任何持久化 IO；
  涉及数据库的跨字段业务规则（去重、上限、周期重算）留在 services/。
- 校验失败统一抛 ``core.exceptions.ValidationError``（中文文案与旧版一致）。
- 复用 ``core/domain.py`` 的严格领域校验（金额整数、日期格式、枚举别名等）。
"""
from __future__ import annotations

from ..core.exceptions import ValidationError

__all__ = [
    "CategorySchema",
    "SettingsSchema",
    "SubscriptionSchema",
]
