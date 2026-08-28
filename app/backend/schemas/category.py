"""分类参数校验 Schema。

名称归一化（NFC / 全角转半角 / 非法字符 / 长度）为纯函数；
重名检测与数量上限依赖数据库，在 services/categories 中完成。
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from ..core.exceptions import ValidationError

MAX_CATEGORY_NAME_LEN = 20
MAX_CATEGORIES_PER_USER = 50
_CATEGORY_ILLEGAL_RE = re.compile(r'[<>"\'&]')


def normalize_category_name(name: Any) -> str:
    """NFC 归一化 + 全角转半角 + 去空白 + 非法字符/长度校验。"""
    raw = str(name or "")
    norm = unicodedata.normalize("NFC", raw).strip()
    converted = []
    for ch in norm:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            converted.append(chr(code - 0xFEE0))
        elif code == 0x3000:
            converted.append(" ")
        else:
            converted.append(ch)
    normalized = "".join(converted).strip()
    if not normalized:
        raise ValidationError("分类名称不能为空")
    if len([*normalized]) > MAX_CATEGORY_NAME_LEN:
        raise ValidationError(f"分类名称最多{MAX_CATEGORY_NAME_LEN}字")
    if _CATEGORY_ILLEGAL_RE.search(normalized):
        raise ValidationError("分类名称不能包含 < > \" ' &")
    return normalized


def normalize_icon(icon: Any) -> str | None:
    """图标限 1 个 emoji。"""
    if icon is None or str(icon).strip() == "":
        return None
    value = str(icon).strip()
    if len([*value]) > 2:
        raise ValidationError("图标限1-2个emoji")
    if re.fullmatch(r"[a-zA-Z0-9]+", value):
        raise ValidationError("图标请使用 emoji，如 \U0001f3ac")
    return [*value][0]


def normalize_sort_order(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
