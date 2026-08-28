"""Schema 基类与公共工具。"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..core.exceptions import ValidationError

MAX_NOTES_LENGTH = 120


def require_mapping(data: Any) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        raise ValidationError("请求数据必须是对象")
    return data


def reject_explicit_blank(data: Mapping[str, Any], fields: tuple[str, ...]) -> None:
    """显式传 null / 空白字符串的必填字段直接拒绝。"""
    for field in fields:
        if field in data and data[field] is None:
            raise ValidationError(f"{field}不能为空")
        if field in data and isinstance(data[field], str) and not data[field].strip():
            raise ValidationError(f"{field}不能为空")


def optional_text(value: Any, field: str | None = None,
                  max_length: int | None = None) -> str | None:
    """可选文本字段：空白归一为 None，超长拒绝。"""
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    if max_length is not None and len(text) > max_length:
        raise ValidationError(f"{field or '字段'}不能超过{max_length}字")
    return text
