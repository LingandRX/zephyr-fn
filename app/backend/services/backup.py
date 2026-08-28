"""备份与导入导出服务。

本模块负责备份文件以及订阅/分类数据的序列化、反序列化与合并。
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from ..core import domain
from ..extensions import db
from ..models import Category, Subscription
from ..storage import repositories


MAX_IMPORT_ROWS = 10_000
MAX_NAME_LENGTH = 200
MAX_CATEGORY_NAME_LENGTH = 120
MAX_NOTES_LENGTH = 120
MAX_ID_LENGTH = 128
MAX_TIMESTAMP_LENGTH = 80

_CURRENCIES = {"CNY", "USD", "HKD"}
_BILLING_STATUSES = {"normal", "paid", "overdue"}

_PERIOD_ALIASES = {
    **{key: key for key in domain.PERIOD_TYPES},
    **{str(label).strip(): key for key, label in domain.PERIOD_LABELS.items()},
}
_RENEWAL_ALIASES = {
    "auto": "auto",
    "manual": "manual",
    "stop": "stop",
    "stop_on_expiry": "stop_on_expiry",
    "自动续费": "auto",
    "手动续费": "manual",
    "到期停止": "stop",
}
_BILLING_ALIASES = {
    "normal": "normal",
    "paid": "paid",
    "overdue": "overdue",
    "正常": "normal",
    "已支付": "paid",
    "逾期": "overdue",
}
_LIFECYCLE_ALIASES = {
    **{key: key for key in domain.LIFECYCLES},
    **{str(label).strip(): key for key, label in domain.STATUS_LABELS.items()
       if key in domain.LIFECYCLES},
}

_SUBSCRIPTION_COLUMNS = (
    "id", "user_id", "name", "amount", "currency", "actual_amount",
    "category_id", "notes", "period_type", "custom_period_value",
    "custom_period_unit", "auto_renew", "sharing_role", "sharing_count",
    "start_date", "first_payment_date", "next_due_date", "lifecycle",
    "renewal_policy", "billing_status", "grace_period_ends_at",
    "sync_version", "created_at", "updated_at",
)


def _period_label(period_type: str) -> str:
    return domain.PERIOD_LABELS.get(period_type, period_type)


def _lifecycle_label(value: str) -> str:
    return domain.STATUS_LABELS.get(value, value)


def _renewal_label(value: str) -> str:
    return {
        "auto": "自动续费",
        "manual": "手动续费",
        "stop": "到期停止",
        "stop_on_expiry": "到期停止",
    }.get(value, value)


def _billing_label(value: str) -> str:
    return {"normal": "正常", "paid": "已支付", "overdue": "逾期"}.get(value, value)


def _require_user_id(user_id: str | None) -> str:
    value = str(user_id or "").strip()
    if not value:
        raise ValueError("必须明确指定 user_id")
    if len(value) > MAX_ID_LENGTH:
        raise ValueError("user_id 过长")
    return value


def _resolve_export_scope(user_id: str | None, include_all: bool) -> str | None:
    if include_all:
        if user_id not in (None, ""):
            raise ValueError("user_id 与 include_all 不能同时使用")
        return None
    return _require_user_id(user_id)


def _scoped_records(user_id: str | None, include_all: bool) -> tuple[list[dict], list[dict]]:
    scope = _resolve_export_scope(user_id, include_all)
    if scope is None:
        return repositories.get_all_subscriptions_raw(), repositories.get_all_categories_raw()
    return repositories.get_all_subscriptions(scope), repositories.get_all_categories(scope)


def export_json(user_id: str | None = None, *, include_all: bool = False) -> dict:
    scope = _resolve_export_scope(user_id, include_all)
    subscriptions, categories = _scoped_records(scope, include_all)
    return {
        "app": "subscription-manager",
        "version": "0.1.0",
        "exported_at": repositories.now_utc(),
        "scope": {"user_id": scope, "all_users": scope is None},
        "categories": categories,
        "subscriptions": subscriptions,
    }


def export_json_string(user_id: str | None = None, *, include_all: bool = False) -> str:
    return json.dumps(
        export_json(user_id, include_all=include_all), ensure_ascii=False, indent=2
    )


def export_csv(user_id: str | None = None, *, include_all: bool = False) -> str:
    subscriptions, categories = _scoped_records(user_id, include_all)
    cats = {c["id"]: c["name"] for c in categories}
    buf = io.StringIO(newline="")
    writer = csv.writer(buf)
    writer.writerow([
        "名称", "金额", "货币", "周期类型", "首次付款日", "下次到期日",
        "生命周期", "续费策略", "账单状态", "分类", "备注", "ID",
        "开始日期", "自定义周期值", "自定义周期单位",
    ])
    for sub in subscriptions:
        writer.writerow([
            sub["name"],
            f"{sub['amount'] / 100:.2f}",
            sub["currency"],
            _period_label(sub["period_type"]),
            sub.get("first_payment_date") or "",
            sub.get("next_due_date") or "",
            _lifecycle_label(sub["lifecycle"]),
            _renewal_label(sub["renewal_policy"]),
            _billing_label(sub["billing_status"]),
            cats.get(sub.get("category_id"), "未分类") if sub.get("category_id") else "未分类",
            sub.get("notes") or "",
            sub.get("id") or "",
            sub.get("start_date") or "",
            sub.get("custom_period_value") or "",
            sub.get("custom_period_unit") or "",
        ])
    return "\ufeff" + buf.getvalue()


# --------------------------------------------------------------------------- #
# 输入校验与规范化
# --------------------------------------------------------------------------- #

def _clean_text(value: Any, field: str, *, required: bool = False,
                max_length: int | None = None) -> str | None:
    if value is None:
        text = ""
    else:
        text = str(value).strip()
    if required and not text:
        raise ValueError(f"{field}不能为空")
    if max_length is not None and len(text) > max_length:
        raise ValueError(f"{field}不能超过{max_length}字")
    return text or None


def _clean_external_id(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > MAX_ID_LENGTH:
        raise ValueError("外部 ID 过长")
    return text


def _parse_nonnegative_int(value: Any, field: str, *, allow_none: bool = False,
                           default: int | None = None) -> int | None:
    if value in (None, ""):
        if allow_none:
            return default
        return 0 if default is None else default
    if isinstance(value, bool):
        raise ValueError(f"{field}必须是非负整数")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{field}必须是非负整数")
    text = str(value).strip()
    if not re.fullmatch(r"\+?\d+", text):
        raise ValueError(f"{field}必须是非负整数")
    parsed = int(text)
    if parsed < 0:
        raise ValueError(f"{field}不能为负数")
    return parsed


def _parse_bool(value: Any, field: str, default: bool = False) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "是", "开启"}:
        return True
    if text in {"0", "false", "no", "n", "off", "否", "关闭"}:
        return False
    raise ValueError(f"{field}必须是布尔值")


def _parse_date(value: Any, field: str, *, default: str | None = None,
                allow_none: bool = True) -> str | None:
    if value in (None, ""):
        if default is not None:
            return default
        if allow_none:
            return None
        raise ValueError(f"{field}不能为空")
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    candidate = text
    if len(text) > 10 and text[10] in ("T", " "):
        candidate = text[:10]
    try:
        return date.fromisoformat(candidate).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}必须是 YYYY-MM-DD 日期") from exc


def _clean_timestamp(value: Any, default: str) -> str:
    if value in (None, ""):
        return default
    text = str(value).strip()
    if len(text) > MAX_TIMESTAMP_LENGTH:
        raise ValueError("时间戳过长")
    return text or default


def _canonical(value: Any, aliases: dict[str, str], field: str,
               *, default: str | None = None) -> str | None:
    if value in (None, ""):
        return default
    text = str(value).strip()
    canonical = aliases.get(text) or aliases.get(text.lower())
    if canonical is None:
        raise ValueError(f"未知{field}: {text}")
    return canonical


def _subscription_key(name: str, amount: int, period_type: str) -> str:
    return f"{name.strip()}|{amount}|{period_type}".lower()


def _normalize_imported_sub(raw: dict, user_id: str,
                            category_id: str | None = None) -> dict:
    target_user = _require_user_id(user_id)
    if not isinstance(raw, dict):
        raise ValueError("订阅记录必须是对象")

    name = _clean_text(raw.get("name"), "名称", required=True, max_length=MAX_NAME_LENGTH)
    period_type = _canonical(raw.get("period_type") or "month", _PERIOD_ALIASES, "周期类型")
    currency = str(raw.get("currency") or "CNY").strip().upper()
    if currency not in _CURRENCIES:
        raise ValueError(f"不支持的货币: {currency}")

    amount = _parse_nonnegative_int(raw.get("amount"), "金额", default=0)
    actual_amount = _parse_nonnegative_int(
        raw.get("actual_amount"), "实际金额", allow_none=True
    )
    start_date = _parse_date(
        raw.get("start_date"), "首次日期", default=date.today().isoformat(), allow_none=False
    )
    first_payment_date = _parse_date(raw.get("first_payment_date"), "首次付款日")
    next_due_date = _parse_date(raw.get("next_due_date"), "下次到期日")

    custom_value: int | None = None
    custom_unit: str | None = None
    if period_type == "custom":
        custom_value = _parse_nonnegative_int(
            raw.get("custom_period_value"), "自定义周期值", default=1
        )
        if custom_value < 1:
            raise ValueError("自定义周期值必须大于 0")
        custom_unit = str(raw.get("custom_period_unit") or "month").strip().lower()
        if custom_unit not in domain.CUSTOM_UNITS:
            raise ValueError(f"未知自定义周期单位: {custom_unit}")

    auto_renew = _parse_bool(raw.get("auto_renew"), "auto_renew", default=True)
    explicit_policy = _canonical(
        raw.get("renewal_policy"), _RENEWAL_ALIASES, "续费策略", default=None
    )
    if period_type == "once":
        auto_renew, renewal_policy = False, "manual"
    else:
        auto_renew, renewal_policy = domain.normalize_renewal_on_create(
            auto_renew, explicit_policy
        )

    lifecycle = _canonical(
        raw.get("lifecycle"), _LIFECYCLE_ALIASES, "生命周期", default="active"
    )
    billing_status = _canonical(
        raw.get("billing_status"), _BILLING_ALIASES, "账单状态", default="normal"
    )

    notes = _clean_text(raw.get("notes"), "备注", max_length=MAX_NOTES_LENGTH)
    sharing_role = _clean_text(raw.get("sharing_role"), "共享角色", max_length=64)
    sharing_count = _parse_nonnegative_int(
        raw.get("sharing_count"), "共享人数", allow_none=True
    )
    sync_version = _parse_nonnegative_int(raw.get("sync_version"), "同步版本", default=1)
    if sync_version < 1:
        raise ValueError("同步版本必须大于 0")

    if next_due_date is None and period_type != "once":
        derived = domain.add_one_period(
            date.fromisoformat(start_date), period_type, custom_value, custom_unit
        )
        if derived is not None:
            next_due_date = derived.isoformat()

    external_id = _clean_external_id(raw.get("id")) or repositories.new_id()
    now = repositories.now_utc()
    return {
        "id": external_id,
        "user_id": target_user,
        "name": name,
        "amount": amount,
        "currency": currency,
        "actual_amount": actual_amount,
        "category_id": category_id,
        "notes": notes,
        "period_type": period_type,
        "custom_period_value": custom_value,
        "custom_period_unit": custom_unit,
        "auto_renew": int(auto_renew),
        "sharing_role": sharing_role,
        "sharing_count": sharing_count,
        "start_date": start_date,
        "first_payment_date": first_payment_date,
        "next_due_date": next_due_date,
        "lifecycle": lifecycle,
        "renewal_policy": renewal_policy,
        "billing_status": billing_status,
        "grace_period_ends_at": _clean_timestamp(
            raw.get("grace_period_ends_at"), now
        ) if raw.get("grace_period_ends_at") not in (None, "") else None,
        "sync_version": sync_version,
        "created_at": _clean_timestamp(raw.get("created_at"), now),
        "updated_at": _clean_timestamp(raw.get("updated_at"), now),
    }


# --------------------------------------------------------------------------- #
# 事务与冲突规划
# --------------------------------------------------------------------------- #

def _insert_category_conn(session: Any, category: dict) -> None:
    session.add(Category(
        id=category["id"], user_id=category["user_id"], name=category["name"],
        icon=category.get("icon"), sort_order=category.get("sort_order", 0),
    ))


def _insert_subscription_conn(session: Any, sub: dict) -> None:
    session.add(Subscription(**{column: sub.get(column) for column in _SUBSCRIPTION_COLUMNS}))


def _update_subscription_conn(session: Any, sub: dict, sub_id: str, user_id: str) -> None:
    existing = session.get(Subscription, sub_id)
    if existing is None or existing.user_id != user_id:
        raise ValueError("合并时目标订阅不存在或用户不匹配")
    for column in _SUBSCRIPTION_COLUMNS:
        if column not in ("id", "user_id"):
            setattr(existing, column, sub.get(column))


def _load_existing_subscriptions(user_id: str) -> tuple[dict[str, dict], set[str]]:
    target_user = _require_user_id(user_id)
    rows = repositories.get_all_subscriptions_raw()
    by_id = {str(row["id"]): row for row in rows if row.get("id")}
    keys = {
        _subscription_key(str(row.get("name") or ""), int(row.get("amount") or 0),
                          str(row.get("period_type") or ""))
        for row in rows if row.get("user_id") == target_user
    }
    try:
        keys.update(str(key).lower() for key in repositories.get_subscription_dedup_keys(target_user))
    except Exception:  # noqa: BLE001
        pass
    return by_id, keys


def _load_category_state(user_id: str) -> tuple[dict[str, dict], dict[str, dict], dict[str, dict]]:
    target_user = _require_user_id(user_id)
    all_categories = repositories.get_all_categories_raw()
    target_categories = [c for c in all_categories if c.get("user_id")]
    global_by_id = {str(c["id"]): c for c in all_categories if c.get("id")}
    target_by_id = {str(c["id"]): c for c in target_categories if c.get("id")}
    target_by_name = {
        str(c.get("name") or "").strip(): c for c in target_categories if c.get("name")
    }
    return global_by_id, target_by_id, target_by_name


def _category_name(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text or text == "未分类":
        return None
    if len(text) > MAX_CATEGORY_NAME_LENGTH:
        raise ValueError(f"分类不能超过{MAX_CATEGORY_NAME_LENGTH}字")
    return text


def _plan_categories(user_id: str, categories_in: list[Any],
                     referenced_names: set[str]) -> tuple[dict[str, str], dict[str, str],
                                                          list[dict], int]:
    target_user = _require_user_id(user_id)
    global_by_id, target_by_id, target_by_name = _load_category_state(target_user)
    source_to_target: dict[str, str] = {}
    name_to_target: dict[str, str] = {
        name: str(category["id"]) for name, category in target_by_name.items()
    }
    pending: list[dict] = []
    pending_names: dict[str, str] = {}
    conflicts = 0

    def ensure_category(name: str, source_id: str | None = None,
                        icon: Any = None, sort_order: Any = 0) -> str:
        nonlocal conflicts
        if name in name_to_target:
            target_id = name_to_target[name]
            if source_id:
                source_to_target[source_id] = target_id
            return target_id

        target_id = source_id
        if target_id and target_id in global_by_id:
            if (global_by_id[target_id].get("user_id") != target_user
                    or target_by_id.get(target_id, {}).get("name") != name):
                conflicts += 1
                target_id = None
        if not target_id:
            target_id = repositories.new_id()
        if target_id in pending_names.values():
            if source_id:
                source_to_target[source_id] = target_id
            return target_id

        category = {
            "id": target_id,
            "user_id": target_user,
            "name": name,
            "icon": icon,
            "sort_order": _safe_sort_order(sort_order),
        }
        pending.append(category)
        pending_names[name] = target_id
        name_to_target[name] = target_id
        if source_id:
            source_to_target[source_id] = target_id
        return target_id

    for raw in categories_in:
        if not isinstance(raw, dict):
            continue
        try:
            name = _category_name(raw.get("name"))
            if not name:
                continue
            source_id = _clean_external_id(raw.get("id"))
            ensure_category(name, source_id, raw.get("icon"), raw.get("sort_order", 0))
        except ValueError:
            continue

    for name in sorted(referenced_names):
        ensure_category(name)

    return source_to_target, name_to_target, pending, conflicts


def _safe_sort_order(value: Any) -> int:
    try:
        parsed = _parse_nonnegative_int(value, "分类排序", default=0)
        return parsed if parsed is not None else 0
    except ValueError:
        return 0


def _resolve_category_id(source_id: Any, source_to_target: dict[str, str],
                         target_user: str) -> str | None:
    if source_id in (None, ""):
        return None
    source = _clean_external_id(source_id)
    if not source:
        return None
    target = source_to_target.get(source)
    if target:
        return target
    try:
        for category in repositories.get_all_categories(target_user):
            if str(category.get("id")) == source:
                return source
    except Exception:  # noqa: BLE001
        pass
    return None


def _prepare_subscription_items(raw_items: list[Any], user_id: str,
                                existing_by_id: dict[str, dict],
                                existing_keys: set[str],
                                source_name: str,
                                category_id_map: dict[str, str],
                                category_name_map: dict[str, str]) -> tuple[list[dict], list[dict], int, int]:
    target_user = _require_user_id(user_id)
    planned: list[dict] = []
    failed: list[dict] = []
    skipped = 0
    id_conflicts = 0
    used_ids = set(existing_by_id)

    for index, raw in enumerate(raw_items, start=1):
        row_number = index if source_name == "json" else index + 1
        if not isinstance(raw, dict):
            skipped += 1
            failed.append({"row": row_number, "reason": "订阅记录必须是对象"})
            continue
        try:
            source_id = _clean_external_id(raw.get("id"))
            category_name = _category_name(
                raw.get("_category_name") if "_category_name" in raw
                else raw.get("category_name")
            )
            category_id = _resolve_category_id(
                raw.get("category_id"), category_id_map, target_user
            )
            if category_id is None and category_name:
                category_id = category_name_map.get(category_name)
            sub = _normalize_imported_sub(raw, target_user, category_id)
            key = _subscription_key(sub["name"], sub["amount"], sub["period_type"])
            if key in existing_keys:
                skipped += 1
                continue

            if source_id is None:
                sub["id"] = repositories.new_id()
            elif source_id in used_ids:
                sub["id"] = repositories.new_id()
                id_conflicts += 1
            else:
                sub["id"] = source_id
            used_ids.add(sub["id"])
            existing_keys.add(key)
            planned.append(sub)
        except (TypeError, ValueError, KeyError) as exc:
            skipped += 1
            failed.append({"row": row_number, "reason": str(exc)})

    return planned, failed, skipped, id_conflicts


def _commit_import(categories: list[dict], subscriptions: list[dict]) -> tuple[bool, str | None, bool]:
    """在单个事务中写入导入数据；失败整体回滚。"""
    if not categories and not subscriptions:
        return True, None, True
    try:
        for category in categories:
            _insert_category_conn(db.session, category)
        for sub in subscriptions:
            _insert_subscription_conn(db.session, sub)
        db.session.commit()
        return True, None, True
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        return False, str(exc), True


def _import_result(success_count: int = 0, skipped_duplicates: int = 0,
                  added_categories: int = 0, failed_rows: list[dict] | None = None,
                  id_conflicts: int = 0, category_conflicts: int = 0,
                  *, error: str | None = None, atomic: bool = True) -> dict:
    result = {
        "success_count": success_count,
        "skipped_duplicates": skipped_duplicates,
        "added_categories": added_categories,
        "failed_rows": failed_rows or [],
        "id_conflicts": id_conflicts,
        "category_conflicts": category_conflicts,
        "atomic": atomic,
    }
    if error:
        result["error"] = error
    return result


# --------------------------------------------------------------------------- #
# 备份文件管理
# --------------------------------------------------------------------------- #

def resolve_backup_file(name: str) -> Path:
    """把备份文件名解析为备份目录内的安全路径，防止路径穿越。"""
    from .. import config as app_config
    filename = os.path.basename(str(name or "").strip())
    if not filename.startswith("subscription-") or filename == "subscription-":
        raise ValueError("非法的备份文件名")
    if filename in (".", "..") or "/" in filename or "\\" in filename:
        raise ValueError("非法的备份文件名")
    backup_dir = app_config.backup_dir().resolve()
    path = (backup_dir / filename).resolve()
    if path.parent != backup_dir:
        raise ValueError("非法的备份文件路径")
    return path


def delete_backup_file(name: str) -> bool:
    path = resolve_backup_file(name)
    if not path.is_file():
        return False
    path.unlink()
    return True


def list_backup_files() -> list[dict]:
    from .. import config as app_config
    backup_dir = app_config.backup_dir()
    if not backup_dir.exists():
        return []
    files = []
    for p in sorted(backup_dir.glob("subscription-*"), reverse=True)[:50]:
        files.append({
            "name": p.name,
            "size": p.stat().st_size,
            "modified": p.stat().st_mtime,
        })
    return files


# --------------------------------------------------------------------------- #
# JSON 导入
# --------------------------------------------------------------------------- #

def import_from_json(json_data: str, user_id: str) -> dict:
    try:
        target_user = _require_user_id(user_id)
    except ValueError as exc:
        return _import_result(error=str(exc))

    try:
        payload = json.loads(json_data)
    except (TypeError, json.JSONDecodeError) as exc:
        return _import_result(error=f"JSON 解析失败: {exc}")

    if isinstance(payload, dict):
        subs_in = payload.get("subscriptions", [])
        cats_in = payload.get("categories", [])
    elif isinstance(payload, list):
        subs_in = payload
        cats_in = []
    else:
        return _import_result(error="JSON 根节点必须是对象或订阅数组")

    if not isinstance(subs_in, list) or not isinstance(cats_in, list):
        return _import_result(error="subscriptions/categories 必须是数组")
    if len(subs_in) > MAX_IMPORT_ROWS or len(cats_in) > MAX_IMPORT_ROWS:
        return _import_result(error=f"导入记录不能超过 {MAX_IMPORT_ROWS} 条")

    try:
        existing_by_id, existing_keys = _load_existing_subscriptions(target_user)
        source_to_target, category_name_map, pending_categories, category_conflicts = (
            _plan_categories(target_user, cats_in, set())
        )
        planned, failed, skipped, id_conflicts = _prepare_subscription_items(
            subs_in, target_user, existing_by_id, existing_keys, "json",
            source_to_target, category_name_map,
        )
        ok, error, atomic = _commit_import(pending_categories, planned)
        if not ok:
            return _import_result(
                skipped_duplicates=skipped, failed_rows=failed,
                id_conflicts=id_conflicts, category_conflicts=category_conflicts,
                error=f"导入事务失败: {error}", atomic=atomic,
            )
        return _import_result(
            success_count=len(planned), skipped_duplicates=skipped,
            added_categories=len(pending_categories), failed_rows=failed,
            id_conflicts=id_conflicts, category_conflicts=category_conflicts,
            atomic=atomic,
        )
    except Exception as exc:  # noqa: BLE001
        return _import_result(error=f"导入失败: {exc}")


# --------------------------------------------------------------------------- #
# CSV 导入
# --------------------------------------------------------------------------- #

def _parse_csv_amount(value: str) -> int:
    text = (value or "").strip()
    if not text:
        return 0
    try:
        amount = Decimal(text.replace(",", ""))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("金额格式无效") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("金额不能为负数")
    cents = (amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if cents < 0 or cents > Decimal("9223372036854775807"):
        raise ValueError("金额超出范围")
    return int(cents)


def _col(row: list[str], columns: dict[str, int], name: str) -> str:
    index = columns.get(name)
    if index is None or index >= len(row):
        return ""
    return (row[index] or "").strip()


def _read_csv_rows(csv_data: str) -> tuple[list[str], list[list[str]]]:
    text = str(csv_data or "").lstrip("\ufeff")
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        header = next(reader)
    except StopIteration:
        return [], []
    rows: list[list[str]] = []
    for row_number, row in enumerate(reader, start=2):
        if row_number > MAX_IMPORT_ROWS + 1:
            raise ValueError(f"CSV 行数不能超过 {MAX_IMPORT_ROWS} 条")
        rows.append(row)
    return [str(h).strip() for h in header], rows


def import_from_csv(csv_data: str, user_id: str) -> dict:
    try:
        target_user = _require_user_id(user_id)
        header, rows = _read_csv_rows(csv_data)
    except (TypeError, ValueError, csv.Error) as exc:
        return _import_result(error=f"CSV 解析失败: {exc}")
    if not header:
        return _import_result()

    columns = {name: index for index, name in enumerate(header) if name}
    if "名称" not in columns or "金额" not in columns:
        return _import_result(error="CSV 缺少必要列：名称、金额")

    raw_items: list[dict] = []
    failed: list[dict] = []
    for row_index, row in enumerate(rows, start=2):
        try:
            name = _col(row, columns, "名称")
            if not name:
                raise ValueError("名称为空")
            period_type = _canonical(
                _col(row, columns, "周期类型") or "month", _PERIOD_ALIASES, "周期类型"
            )
            renewal_policy = _canonical(
                _col(row, columns, "续费策略"), _RENEWAL_ALIASES, "续费策略", default=None
            )
            billing_status = _canonical(
                _col(row, columns, "账单状态"), _BILLING_ALIASES, "账单状态", default="normal"
            )
            lifecycle = _canonical(
                _col(row, columns, "生命周期"), _LIFECYCLE_ALIASES, "生命周期", default="active"
            )
            category_name = _category_name(_col(row, columns, "分类"))
            raw_items.append({
                "id": _col(row, columns, "ID") or None,
                "name": name,
                "amount": _parse_csv_amount(_col(row, columns, "金额")),
                "currency": (_col(row, columns, "货币") or "CNY").upper(),
                "period_type": period_type,
                "first_payment_date": _col(row, columns, "首次付款日") or None,
                "next_due_date": _col(row, columns, "下次到期日") or None,
                "start_date": (
                    _col(row, columns, "开始日期")
                    or _col(row, columns, "首次付款日")
                    or None
                ),
                "custom_period_value": _col(row, columns, "自定义周期值") or None,
                "custom_period_unit": _col(row, columns, "自定义周期单位") or None,
                "lifecycle": lifecycle,
                "renewal_policy": renewal_policy,
                "billing_status": billing_status,
                "notes": _col(row, columns, "备注") or None,
                "_category_name": category_name,
                "auto_renew": renewal_policy == "auto" if renewal_policy else True,
            })
        except (TypeError, ValueError) as exc:
            failed.append({"row": row_index, "reason": str(exc)})

    try:
        existing_by_id, existing_keys = _load_existing_subscriptions(target_user)
        referenced_names = {
            str(item["_category_name"]) for item in raw_items if item.get("_category_name")
        }
        source_to_target, category_name_map, pending_categories, category_conflicts = (
            _plan_categories(target_user, [], referenced_names)
        )
        planned, failed_rows, skipped, id_conflicts = _prepare_subscription_items(
            raw_items, target_user, existing_by_id, existing_keys, "csv",
            source_to_target, category_name_map,
        )
        failed.extend(failed_rows)
        ok, error, atomic = _commit_import(pending_categories, planned)
        if not ok:
            return _import_result(
                skipped_duplicates=skipped, failed_rows=failed,
                id_conflicts=id_conflicts, category_conflicts=category_conflicts,
                error=f"导入事务失败: {error}", atomic=atomic,
            )
        return _import_result(
            success_count=len(planned), skipped_duplicates=skipped,
            added_categories=len(pending_categories), failed_rows=failed,
            id_conflicts=id_conflicts, category_conflicts=category_conflicts,
            atomic=atomic,
        )
    except Exception as exc:  # noqa: BLE001
        return _import_result(
            skipped_duplicates=0, failed_rows=failed, error=f"导入失败: {exc}", atomic=False
        )


# --------------------------------------------------------------------------- #
# 从 .db 备份文件合并
# --------------------------------------------------------------------------- #

def _is_newer(source: dict, current: dict) -> bool:
    return str(source.get("updated_at") or "") > str(current.get("updated_at") or "")


def merge_from_database(source_path: str, user_id: str) -> str:
    """按 ``id/updated_at`` 合并 SQLite 备份。"""
    try:
        target_user = _require_user_id(user_id)
    except ValueError as exc:
        return f"合并失败：{exc}"

    path = Path(source_path)
    if not path.is_file():
        return f"合并失败：备份文件不存在: {path}"

    src: sqlite3.Connection | None = None
    try:
        src = sqlite3.connect(str(path))
        src.row_factory = sqlite3.Row
        tables = {
            row[0] for row in src.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "subscriptions" not in tables or "categories" not in tables:
            return "合并失败：备份数据库缺少必要表"
        backup_subs = [dict(row) for row in src.execute("SELECT * FROM subscriptions").fetchall()]
        backup_cats = [dict(row) for row in src.execute("SELECT * FROM categories").fetchall()]
    except (OSError, sqlite3.Error) as exc:
        return f"合并失败：无法读取备份数据库: {exc}"
    finally:
        if src is not None:
            src.close()

    if len(backup_subs) > MAX_IMPORT_ROWS or len(backup_cats) > MAX_IMPORT_ROWS:
        return f"合并失败：备份记录不能超过 {MAX_IMPORT_ROWS} 条"

    try:
        existing_by_id, _existing_keys = _load_existing_subscriptions(target_user)
        source_to_target, _category_name_map, pending_categories, category_conflicts = (
            _plan_categories(target_user, backup_cats, set())
        )
        normalized: list[dict] = []
        failed = 0
        for raw in backup_subs:
            try:
                category_id = _resolve_category_id(
                    raw.get("category_id"), source_to_target, target_user
                )
                normalized.append(_normalize_imported_sub(raw, target_user, category_id))
            except (TypeError, ValueError, KeyError):
                failed += 1

        added = updated = skipped = id_conflicts = 0
        to_insert: list[dict] = []
        to_update: list[tuple[dict, str]] = []
        used_ids = set(existing_by_id)
        for sub in normalized:
            source_id = str(sub["id"])
            current = existing_by_id.get(source_id)
            if current is None and source_id not in used_ids:
                to_insert.append(sub)
                used_ids.add(source_id)
                added += 1
                continue
            if current is not None and current.get("user_id") == target_user:
                if _is_newer(sub, current):
                    to_update.append((sub, source_id))
                    updated += 1
                else:
                    skipped += 1
                continue
            sub["id"] = repositories.new_id()
            while sub["id"] in used_ids:
                sub["id"] = repositories.new_id()
            used_ids.add(sub["id"])
            to_insert.append(sub)
            id_conflicts += 1
            added += 1

        try:
            for category in pending_categories:
                _insert_category_conn(db.session, category)
            for sub in to_insert:
                _insert_subscription_conn(db.session, sub)
            for sub, sub_id in to_update:
                _update_subscription_conn(db.session, sub, sub_id, target_user)
            db.session.commit()
            atomic = True
        except Exception as exc:  # noqa: BLE001
            db.session.rollback()
            return f"合并失败：事务回滚: {exc}"

        suffix = f"，跳过无效 {failed} 条" if failed else ""
        non_atomic = "（兼容模式，非原子）" if not atomic else ""
        return (
            f"合并完成{non_atomic}：订阅添加 {added} 条、更新 {updated} 条、"
            f"跳过 {skipped} 条；类别添加 {len(pending_categories)} 个、"
            f"分类 ID 冲突 {category_conflicts} 个、订阅 ID 冲突 {id_conflicts} 个{suffix}"
        )
    except Exception as exc:  # noqa: BLE001
        return f"合并失败：{exc}"
