#!/usr/bin/env python3
"""生成 20 条演示订阅数据。

用法：
  # 1) 生成 demo-data.json（可在真机应用「设置 -> 备份与数据 -> 导入 JSON」使用）
  python3 tools/seed_demo_data.py

  # 2) 直接灌入本地/指定数据库（走 import_from_json 去重逻辑）
  python3 tools/seed_demo_data.py --db ./data/subscription.db --user local
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "app" / "backend"))


def _id() -> str:
    return uuid.uuid4().hex


def build_demo_data() -> dict:
    """20 条订阅 + 9 个分类，格式与备份导出 JSON 一致。"""
    cats = [
        {"id": _id(), "user_id": "local", "name": "流媒体", "icon": "🎬", "sort_order": 1},
        {"id": _id(), "user_id": "local", "name": "云存储", "icon": "☁️", "sort_order": 2},
        {"id": _id(), "user_id": "local", "name": "AI 工具", "icon": "🤖", "sort_order": 3},
        {"id": _id(), "user_id": "local", "name": "音乐", "icon": "🎵", "sort_order": 4},
        {"id": _id(), "user_id": "local", "name": "办公", "icon": "💼", "sort_order": 5},
        {"id": _id(), "user_id": "local", "name": "开发工具", "icon": "🛠️", "sort_order": 6},
        {"id": _id(), "user_id": "local", "name": "游戏", "icon": "🎮", "sort_order": 7},
        {"id": _id(), "user_id": "local", "name": "健身", "icon": "💪", "sort_order": 8},
        {"id": _id(), "user_id": "local", "name": "电商会员", "icon": "🛒", "sort_order": 9},
        {"id": _id(), "user_id": "local", "name": "其他", "icon": "📦", "sort_order": 10},
    ]
    cat = {c["name"]: c["id"] for c in cats}

    def sub(name, amount, currency, period, cat_name, due, start="2026-01-01",
            auto=True, policy=None, notes=None, lifecycle="active", custom_value=None,
            custom_unit=None, first_pay=None, actual=None):
        return {
            "id": _id(), "user_id": "local", "name": name,
            "amount": int(round(amount * 100)), "currency": currency,
            "actual_amount": int(round(actual * 100)) if actual else None,
            "category_id": cat[cat_name], "notes": notes,
            "period_type": period, "custom_period_value": custom_value,
            "custom_period_unit": custom_unit,
            "auto_renew": int(auto), "sharing_role": None, "sharing_count": None,
            "start_date": start, "first_payment_date": first_pay, "next_due_date": due,
            "lifecycle": lifecycle,
            "renewal_policy": policy or ("auto" if auto else "manual"),
            "billing_status": "normal", "grace_period_ends_at": None,
            "sync_version": 1,
            "created_at": "2026-08-01T08:00:00Z",
            "updated_at": "2026-08-01T08:00:00Z",
        }

    subs = [
        sub("Netflix 标准版", 68, "CNY", "month", "流媒体", "2026-08-15",
            start="2025-03-10", notes="家庭共享，4K 套餐"),
        sub("百度网盘超级会员", 30, "CNY", "month", "云存储", "2026-08-05",
            start="2025-06-01", notes="已逾期，待续费"),
        sub("爱奇艺黄金会员", 25, "CNY", "month", "流媒体", "2026-08-28",
            start="2025-09-01"),
        sub("YouTube Premium", 22.99, "USD", "month", "流媒体", "2026-08-20",
            start="2025-11-15", actual=22.99),
        sub("iCloud+ 200GB", 21, "CNY", "month", "云存储", "2026-09-01",
            start="2025-05-01", notes="家庭共享"),
        sub("ChatGPT Plus", 20, "USD", "month", "AI 工具", "2026-08-16",
            start="2026-02-01", actual=20),
        sub("GitHub Copilot", 10, "USD", "month", "开发工具", "2026-08-17",
            start="2025-07-01", actual=10),
        sub("JetBrains All Products", 1599, "CNY", "year", "开发工具", "2026-12-01",
            start="2025-12-01", notes="个人版年度授权"),
        sub("网易云音乐黑胶VIP", 15, "CNY", "month", "音乐", "2026-08-25",
            start="2025-04-01"),
        sub("Apple Music 学生版", 5.99, "USD", "month", "音乐", "2026-09-05",
            start="2025-08-15", actual=5.99),
        sub("Microsoft 365 家庭版", 398, "CNY", "year", "办公", "2027-02-01",
            start="2026-02-01", notes="6 人家庭组"),
        sub("印象笔记专业版", 98, "CNY", "year", "办公", "2026-10-01",
            start="2025-10-01"),
        sub("PlayStation Plus 三档", 308, "CNY", "quarter", "游戏", "2026-11-01",
            start="2025-11-01"),
        sub("Xbox Game Pass Ultimate", 79, "CNY", "month", "游戏", "2026-08-19",
            start="2025-10-20"),
        sub("Keep 会员", 25, "CNY", "month", "健身", "2026-08-22",
            start="2026-01-10"),
        sub("京东 PLUS 会员", 149, "CNY", "year", "电商会员", "2027-01-15",
            start="2026-01-15"),
        sub("淘宝 88VIP", 888, "CNY", "year", "电商会员", "2026-12-31",
            start="2025-12-31"),
        sub("Adobe Creative Cloud 摄影", 68, "HKD", "month", "办公", "2026-08-30",
            start="2025-09-01", actual=68),
        sub("云服务器 2C4G", 120, "CNY", "custom", "开发工具", "2026-08-18",
            start="2025-03-01", custom_value=30, custom_unit="day",
            notes="自建服务 / 博客"),
        sub("旧工具订阅", 19, "CNY", "month", "其他", None,
            start="2024-05-01", auto=False, policy="stop", lifecycle="canceled",
            notes="已取消的服务"),
    ]
    assert len(subs) == 20, f"期望 20 条，实际 {len(subs)}"
    return {
        "app": "subscription-manager",
        "version": "0.1.1",
        "exported_at": date.today().isoformat() + "T00:00:00Z",
        "categories": cats,
        "subscriptions": subs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 20 条演示订阅数据")
    parser.add_argument("--out", default=str(REPO_ROOT / "data" / "demo-data.json"),
                        help="JSON 导出文件路径（默认 data/demo-data.json）")
    parser.add_argument("--db", help="如提供，直接灌入该 SQLite 数据库")
    parser.add_argument("--user", default="local", help="灌库时的用户 ID（默认 local）")
    args = parser.parse_args()

    data = build_demo_data()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成 JSON 导出文件: {out}（订阅 {len(data['subscriptions'])} 条，"
          f"分类 {len(data['categories'])} 个）")

    if args.db:
        from services.backup import import_from_json
        from storage import db
        db.connect(Path(args.db))
        result = import_from_json(
            json.dumps(data, ensure_ascii=False), args.user
        )
        print(f"已灌入数据库 {args.db}: 新增订阅 {result['success_count']} 条，"
              f"跳过重复 {result['skipped_duplicates']} 条，"
              f"新增分类 {result['added_categories']} 个")



if __name__ == "__main__":
    main()
