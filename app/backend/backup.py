"""备份与导入导出（移植自 zephyr-tarui 的 backup.rs）。

提供：
- export_json / export_csv：导出订阅与分类
- import_json / import_csv：按去重键去重导入
- merge_from_database：从备份的 .db 文件按 id/updated_at 合并
"""
from __future__ import annotations

import csv
import io
import json
import sqlite3
from datetime import date
from typing import Any

import db
import domain


def _period_label(p: str) -> str:
    return domain.PERIOD_LABELS.get(p, p)


def _lifecycle_label(v: str) -> str:
    return domain.STATUS_LABELS.get(v, v)


def _renewal_label(v: str) -> str:
    return {"auto": "自动续费", "manual": "手动续费", "stop": "到期停止",
            "stop_on_expiry": "到期停止"}.get(v, v)


def _billing_label(v: str) -> str:
    return {"normal": "正常", "paid": "已支付", "overdue": "逾期"}.get(v, v)


def export_json() -> dict:
    return {
        "app": "subscription-manager",
        "version": "0.1.0",
        "exported_at": db.now_utc(),
        "categories": db.get_all_categories_raw(),
        "subscriptions": db.get_all_subscriptions_raw(),
    }


def export_json_string() -> str:
    return json.dumps(export_json(), ensure_ascii=False, indent=2)


def export_csv() -> str:
    subs = db.get_all_subscriptions_raw()
    cats = {c["id"]: c["name"] for c in db.get_all_categories_raw()}
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["名称", "金额", "货币", "周期类型", "首次付款日", "下次到期日",
                     "生命周期", "续费策略", "账单状态", "分类", "备注"])
    for sub in subs:
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
            cats.get(sub["category_id"], "未分类") if sub["category_id"] else "未分类",
            sub.get("notes") or "",
        ])
    return "\ufeff" + buf.getvalue()


# --------------------------------------------------------------------------- #
# JSON 导入
# --------------------------------------------------------------------------- #

def import_from_json(json_data: str, user_id: str) -> dict:
    try:
        payload = json.loads(json_data)
    except json.JSONDecodeError as exc:
        return {"success_count": 0, "skipped_duplicates": 0, "error": f"JSON 解析失败: {exc}"}

    subs_in = payload.get("subscriptions", []) if isinstance(payload, dict) else payload
    cats_in = payload.get("categories", []) if isinstance(payload, dict) else []

    existing_keys = db.get_subscription_dedup_keys(user_id)

    added_cats = 0
    existing_cat_ids = {c["id"] for c in db.get_all_categories(user_id)}
    for cat in cats_in:
        if not cat.get("id") or cat["id"] in existing_cat_ids:
            continue
        db.insert_category_raw({
            "id": cat["id"], "user_id": user_id, "name": cat.get("name", "未分类"),
            "icon": cat.get("icon"), "sort_order": cat.get("sort_order", 0),
        })
        existing_cat_ids.add(cat["id"])
        added_cats += 1

    success = 0
    skipped = 0
    for raw in subs_in:
        if not isinstance(raw, dict) or not raw.get("name"):
            skipped += 1
            continue
        key = f"{raw['name']}|{raw.get('amount', 0)}|{raw.get('period_type', 'month')}".lower()
        if key in existing_keys:
            skipped += 1
            continue
        try:
            sub = _normalize_imported_sub(raw, user_id)
        except ValueError:
            skipped += 1
            continue
        db.insert_subscription_raw(sub)
        existing_keys.add(key)
        success += 1

    return {"success_count": success, "skipped_duplicates": skipped, "added_categories": added_cats}


def _normalize_imported_sub(raw: dict, user_id: str) -> dict:
    name = str(raw.get("name") or "").strip()
    if not name:
        raise ValueError("name required")
    period_type = str(raw.get("period_type") or "month")
    if period_type not in domain.PERIOD_TYPES:
        raise ValueError("bad period_type")
    currency = str(raw.get("currency") or "CNY").upper()
    amount = max(0, int(raw.get("amount") or 0))
    start_date = str(raw.get("start_date") or date.today().isoformat())[:10]
    custom_value = raw.get("custom_period_value")
    custom_value = max(1, int(custom_value)) if custom_value not in (None, "") else None
    custom_unit = raw.get("custom_period_unit") or "month"

    auto_renew = bool(raw.get("auto_renew", True))
    auto_renew, renewal_policy = (
        (False, "manual") if period_type == "once"
        else domain.normalize_renewal_on_create(auto_renew, raw.get("renewal_policy"))
    )

    return {
        "id": str(raw.get("id") or db.new_id()),
        "user_id": user_id,
        "name": name,
        "amount": amount,
        "currency": currency,
        "actual_amount": raw.get("actual_amount"),
        "category_id": raw.get("category_id"),
        "notes": raw.get("notes"),
        "period_type": period_type,
        "custom_period_value": custom_value,
        "custom_period_unit": custom_unit if period_type == "custom" else None,
        "auto_renew": int(auto_renew),
        "sharing_role": raw.get("sharing_role"),
        "sharing_count": raw.get("sharing_count"),
        "start_date": start_date,
        "first_payment_date": str(raw.get("first_payment_date") or "")[:10] or None,
        "next_due_date": str(raw.get("next_due_date") or "")[:10] or None,
        "lifecycle": raw.get("lifecycle") if raw.get("lifecycle") in domain.LIFECYCLES else "active",
        "renewal_policy": renewal_policy,
        "billing_status": raw.get("billing_status", "normal"),
        "grace_period_ends_at": raw.get("grace_period_ends_at"),
        "sync_version": int(raw.get("sync_version") or 1),
        "created_at": raw.get("created_at") or db.now_utc(),
        "updated_at": raw.get("updated_at") or db.now_utc(),
    }


# --------------------------------------------------------------------------- #
# CSV 导入
# --------------------------------------------------------------------------- #

def import_from_csv(csv_data: str, user_id: str) -> dict:
    existing_keys = db.get_subscription_dedup_keys(user_id)
    cats = {c["name"]: c for c in db.get_all_categories(user_id)}

    text = csv_data.lstrip("\ufeff")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return {"success_count": 0, "failed_rows": [], "skipped_duplicates": 0}

    header = [h.strip() for h in rows[0]]
    col = {name: i for i, name in enumerate(header)}
    period_map = {v: k for k, v in domain.PERIOD_LABELS.items()}
    lifecycle_map = {v: k for k, v in domain.STATUS_LABELS.items()}

    success = 0
    failed: list[dict] = []
    skipped = 0
    for idx, row in enumerate(rows[1:], start=2):
        try:
            name = _col(row, col, "名称")
            if not name:
                raise ValueError("名称为空")
            amount = int(round(float(_col(row, col, "金额") or "0") * 100))
            period_label = _col(row, col, "周期类型") or "月付"
            period_type = period_map.get(period_label, "month")
            currency = (_col(row, col, "货币") or "CNY").upper()
            cat_name = _col(row, col, "分类") or "未分类"
            category_id = None
            if cat_name != "未分类":
                if cat_name not in cats:
                    cat = db.create_category(user_id, {"name": cat_name})
                    cats[cat_name] = cat
                category_id = cats[cat_name]["id"]

            key = f"{name}|{amount}|{period_type}".lower()
            if key in existing_keys:
                skipped += 1
                continue

            sub = {
                "name": name, "amount": amount, "currency": currency,
                "period_type": period_type, "category_id": category_id,
                "notes": _col(row, col, "备注"),
                "first_payment_date": _col(row, col, "首次付款日") or None,
                "next_due_date": _col(row, col, "下次到期日") or None,
                "start_date": _col(row, col, "首次付款日") or date.today().isoformat(),
                "lifecycle": lifecycle_map.get(_col(row, col, "生命周期"), "active"),
                "renewal_policy": _col(row, col, "续费策略") or None,
                "billing_status": _col(row, col, "账单状态") or "normal",
            }
            db.insert_subscription_raw(_normalize_imported_sub(sub, user_id))
            existing_keys.add(key)
            success += 1
        except Exception as exc:  # noqa: BLE001 - 单行失败不影响整体
            failed.append({"row": idx, "reason": str(exc)})
    return {"success_count": success, "failed_rows": failed, "skipped_duplicates": skipped}


def _col(row: list, col: dict, name: str) -> str:
    idx = col.get(name)
    if idx is None or idx >= len(row):
        return ""
    return (row[idx] or "").strip()


# --------------------------------------------------------------------------- #
# 从 .db 备份文件合并
# --------------------------------------------------------------------------- #

def merge_from_database(source_path: str, user_id: str) -> str:
    src = sqlite3.connect(source_path)
    src.row_factory = sqlite3.Row
    try:
        backup_subs = [dict(r) for r in src.execute("SELECT * FROM subscriptions").fetchall()]
        backup_cats = [dict(r) for r in src.execute("SELECT * FROM categories").fetchall()]
    finally:
        src.close()

    existing_subs = {s["id"]: s for s in db.get_all_subscriptions_raw()}
    added = updated = skipped = 0
    for sub in backup_subs:
        sub["user_id"] = user_id
        existing = existing_subs.get(sub["id"])
        if existing:
            if (sub.get("updated_at") or "") > (existing.get("updated_at") or ""):
                db.replace_subscription_raw(sub)
                updated += 1
            else:
                skipped += 1
        else:
            db.insert_subscription_raw(sub)
            existing_subs[sub["id"]] = sub
            added += 1

    existing_cat_ids = {c["id"] for c in db.get_all_categories_raw()}
    added_cats = 0
    for cat in backup_cats:
        if cat["id"] not in existing_cat_ids:
            db.insert_category_raw({**cat, "user_id": user_id})
            existing_cat_ids.add(cat["id"])
            added_cats += 1

    return (f"合并完成：订阅添加 {added} 条、更新 {updated} 条、跳过 {skipped} 条；"
            f"类别添加 {added_cats} 个")
