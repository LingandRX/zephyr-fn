"""后端单元测试（unittest，无网络依赖）。

运行：python3 -m unittest discover -s tests -v
"""

import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from helpers import AppTestCase

from backend import config
from backend.domain import domain
from backend.domain.exceptions import ValidationError
from backend.services import (
    calculate_statistics,
    get_calendar_events,
)
from backend.services import (
    categories as category_service,
)
from backend.services import (
    subscriptions as sub_service,
)
from backend import repositories
from backend.repositories.bootstrap import DEFAULT_CATEGORY_TEMPLATES


class DomainTests(unittest.TestCase):
    def test_add_month_clamps_day(self):
        from datetime import date

        self.assertEqual(domain.add_one_period(date(2026, 1, 31), "month"), date(2026, 2, 28))
        self.assertEqual(domain.add_one_period(date(2026, 8, 31), "month"), date(2026, 9, 30))

    def test_add_months_keeps_thirtieth_after_february(self):
        from datetime import date

        start = date(2026, 1, 30)
        self.assertEqual(domain.billing_anchor_day(start), 30)
        self.assertEqual(domain.add_months(start, 1), date(2026, 2, 28))
        self.assertEqual(domain.add_months(start, 2), date(2026, 3, 30))
        self.assertEqual(domain.add_months(start, 3), date(2026, 4, 30))

        feb = domain.add_months(start, 1)
        self.assertEqual(domain.add_months(feb, 1, anchor_day=30), date(2026, 3, 30))
        self.assertEqual(domain.add_one_period(feb, "month", anchor_day=30), date(2026, 3, 30))
        self.assertEqual(domain.sub_one_period(feb, "month", anchor_day=30), start)

    def test_add_months_keeps_month_end_anchor(self):
        from datetime import date

        start = date(2026, 1, 31)
        self.assertEqual(domain.billing_anchor_day(start), 31)
        self.assertEqual(domain.add_months(start, 1), date(2026, 2, 28))
        self.assertEqual(domain.add_months(start, 2), date(2026, 3, 31))
        self.assertEqual(
            domain.add_months(date(2026, 2, 28), 1, anchor_day=31),
            date(2026, 3, 31),
        )
        # 中间结果若不传锚点，2 月 28 日仍按月末处理（兼容旧行为）
        self.assertEqual(domain.add_months(date(2026, 2, 28), 1), date(2026, 3, 31))

    def test_add_months_leap_day_and_negative(self):
        from datetime import date

        self.assertEqual(domain.add_months(date(2024, 1, 29), 1), date(2024, 2, 29))
        self.assertEqual(domain.add_months(date(2024, 1, 29), 2), date(2024, 3, 29))
        self.assertEqual(domain.add_months(date(2024, 2, 29), 1, anchor_day=29), date(2024, 3, 29))
        self.assertEqual(domain.add_months(date(2026, 3, 30), -1), date(2026, 2, 28))
        self.assertEqual(
            domain.add_months(date(2026, 2, 28), -1, anchor_day=30),
            date(2026, 1, 30),
        )
        self.assertEqual(domain.add_months(date(2026, 1, 31), -1), date(2025, 12, 31))

    def test_add_months_rejects_invalid_anchor_day(self):
        from datetime import date

        with self.assertRaisesRegex(ValueError, "锚点日"):
            domain.add_months(date(2026, 1, 30), 1, anchor_day=0)
        with self.assertRaisesRegex(ValueError, "锚点日"):
            domain.add_months(date(2026, 1, 30), 1, anchor_day=32)

    def test_add_quarter_year(self):
        from datetime import date

        self.assertEqual(domain.add_one_period(date(2026, 2, 14), "quarter"), date(2026, 5, 14))
        self.assertEqual(domain.add_one_period(date(2026, 2, 14), "year"), date(2027, 2, 14))

    def test_once_has_no_next(self):
        from datetime import date

        self.assertIsNone(domain.add_one_period(date(2026, 1, 31), "once"))

    def test_custom_period(self):
        from datetime import date

        self.assertEqual(
            domain.add_one_period(date(2026, 3, 1), "custom", 2, "week"), date(2026, 3, 15)
        )
        self.assertEqual(
            domain.add_one_period(date(2026, 3, 1), "custom", 2, "month"), date(2026, 5, 1)
        )

    def test_sub_is_inverse(self):
        from datetime import date

        d = date(2026, 5, 20)
        fwd = domain.add_one_period(d, "month")
        self.assertEqual(domain.sub_one_period(fwd, "month"), d)

    def test_normalize_renewal(self):
        self.assertEqual(domain.normalize_renewal_on_create(True, "stop"), (False, "stop"))
        self.assertEqual(domain.normalize_renewal_on_create(True, None), (True, "auto"))
        self.assertEqual(domain.normalize_renewal_on_create(False, None), (False, "manual"))
        # 验证单一事实来源：显式 renewal_policy 始终覆盖 auto_renew
        self.assertEqual(domain.normalize_renewal_on_create(False, "auto"), (True, "auto"))
        self.assertEqual(domain.normalize_renewal_on_create(True, "manual"), (False, "manual"))
        self.assertTrue(domain.should_auto_renew_on_wake("auto"))
        self.assertTrue(domain.should_auto_renew_on_wake(False, "auto"))
        self.assertFalse(domain.should_auto_renew_on_wake(True, "manual"))

    def test_derive_status(self):
        from datetime import date, timedelta

        today = date.today()
        soon = (today + timedelta(days=3)).isoformat()
        later = (today + timedelta(days=30)).isoformat()
        self.assertEqual(domain.derive_status("active", soon), "expiring")
        self.assertEqual(domain.derive_status("active", later), "active")
        self.assertEqual(domain.derive_status("canceled", later), "canceled")


class SubscriptionServiceTests(AppTestCase):
    def test_create_and_get(self):
        sub = sub_service.create_subscription(
            "u1",
            {
                "name": "Netflix",
                "amount": 6800,
                "currency": "CNY",
                "period_type": "month",
                "auto_renew": True,
                "start_date": "2026-06-11",
                "next_due_date": "2026-08-15",
            },
        )
        self.assertEqual(sub["amount"], 6800)
        self.assertEqual(sub["renewal_policy"], "auto")
        got = sub_service.get_subscription(sub["id"], "u1")
        self.assertEqual(got["name"], "Netflix")

    def test_multi_user_isolation(self):
        sub_service.create_subscription(
            "alice",
            {"name": "A", "amount": 100, "period_type": "month", "start_date": "2026-01-01"},
        )
        sub_service.create_subscription(
            "bob", {"name": "B", "amount": 200, "period_type": "month", "start_date": "2026-01-01"}
        )
        self.assertEqual([s["name"] for s in sub_service.list_subscriptions("alice")], ["A"])
        self.assertEqual([s["name"] for s in sub_service.list_subscriptions("bob")], ["B"])

    def test_renew_advances(self):
        sub = sub_service.create_subscription(
            "u1",
            {
                "name": "iCloud",
                "amount": 2100,
                "period_type": "year",
                "start_date": "2026-05-01",
                "next_due_date": "2026-09-01",
            },
        )
        renewed = sub_service.renew_subscription(sub["id"], "u1")
        self.assertEqual(renewed["next_due_date"], "2027-09-01")

    def test_renew_keeps_thirtieth_after_february(self):
        sub = sub_service.create_subscription(
            "u1",
            {
                "name": "钳制日",
                "amount": 100,
                "period_type": "month",
                "start_date": "2026-01-30",
                "next_due_date": "2026-02-28",
            },
        )
        renewed = sub_service.renew_subscription(sub["id"], "u1")
        self.assertEqual(renewed["next_due_date"], "2026-03-30")

    def test_once_auto_renew_false(self):
        sub = sub_service.create_subscription(
            "u1",
            {
                "name": "一次性",
                "amount": 100,
                "period_type": "once",
                "auto_renew": True,
                "start_date": "2026-01-01",
            },
        )
        self.assertFalse(sub["auto_renew"])
        self.assertEqual(sub["renewal_policy"], "manual")

    def test_renewal_policy_single_source_of_truth(self):
        user_id = "u_ssot"
        # 1. 冲突输入：传入 auto_renew=False 但显式指定 renewal_policy="auto"
        # 业务以 renewal_policy 为权威，展示层 auto_renew 自动同步矫正为 True
        sub1 = sub_service.create_subscription(
            user_id,
            {
                "name": "SSOT-1",
                "amount": 1000,
                "period_type": "month",
                "auto_renew": False,
                "renewal_policy": "auto",
                "start_date": "2026-01-01",
            },
        )
        self.assertEqual(sub1["renewal_policy"], "auto")
        self.assertTrue(sub1["auto_renew"])
        self.assertTrue(sub1["renewal_confirmed"])

        # 2. 冲突输入：传入 auto_renew=True 但显式指定 renewal_policy="manual"
        # 业务以 renewal_policy 为权威，展示层 auto_renew 自动同步矫正为 False
        sub2 = sub_service.create_subscription(
            user_id,
            {
                "name": "SSOT-2",
                "amount": 1000,
                "period_type": "month",
                "auto_renew": True,
                "renewal_policy": "manual",
                "start_date": "2026-01-01",
            },
        )
        self.assertEqual(sub2["renewal_policy"], "manual")
        self.assertFalse(sub2["auto_renew"])
        self.assertEqual(sub2["renewal_confirmed"], 0)

        # 3. 更新操作：只更新 renewal_policy="stop"，auto_renew 自动同步为 False
        up = sub_service.update_subscription(sub1["id"], user_id, {"renewal_policy": "stop"})
        self.assertEqual(up["renewal_policy"], "stop")
        self.assertFalse(up["auto_renew"])

    def test_switching_from_custom_period_clears_legacy_custom_fields(self):
        sub = sub_service.create_subscription(
            "u1",
            {
                "name": "自定义周期",
                "amount": 100,
                "period_type": "custom",
                "custom_period_value": 2,
                "custom_period_unit": "week",
                "start_date": "2026-01-01",
            },
        )
        updated = sub_service.update_subscription(sub["id"], "u1", {"period_type": "month"})
        self.assertEqual(updated["period_type"], "month")
        self.assertIsNone(updated["custom_period_value"])
        self.assertIsNone(updated["custom_period_unit"])

    def test_notes_are_limited_to_120_characters(self):
        notes = "备" * 120
        sub = sub_service.create_subscription(
            "u1",
            {
                "name": "备注限制",
                "amount": 100,
                "period_type": "month",
                "start_date": "2026-01-01",
                "notes": notes,
            },
        )
        self.assertEqual(sub["notes"], notes)

        with self.assertRaisesRegex(ValidationError, "备注不能超过120字"):
            sub_service.create_subscription(
                "u1",
                {
                    "name": "超长备注",
                    "amount": 100,
                    "period_type": "month",
                    "start_date": "2026-01-01",
                    "notes": "备" * 121,
                },
            )

        with self.assertRaisesRegex(ValidationError, "备注不能超过120字"):
            sub_service.update_subscription(sub["id"], "u1", {"notes": "备" * 121})

    def test_settings_defaults_and_update(self):
        s = repositories.get_app_settings()
        self.assertEqual(s["default_currency"], "CNY")
        repositories.update_app_settings({"notification_days": 5, "exchange_rate_usd": 7.1})
        s = repositories.get_app_settings()
        self.assertEqual(s["notification_days"], 5)
        self.assertAlmostEqual(s["exchange_rate_usd"], 7.1)

    def test_categories(self):
        c = category_service.create_category("u1", {"name": "流媒体", "icon": "🎬"})
        self.assertTrue(c["id"])
        self.assertEqual(len(category_service.list_categories("u1")), 1)
        self.assertTrue(category_service.delete_category(c["id"], "u1"))
        self.assertEqual(len(category_service.list_categories("u1")), 0)


class DefaultCategorySeedTests(AppTestCase):
    """按用户懒播种默认分类（v11 seeded_users 机制）。"""

    def test_new_user_gets_defaults_once(self):
        self.assertTrue(category_service.ensure_default_categories_for_user("u-1000"))
        cats = category_service.list_categories("u-1000")
        self.assertGreaterEqual(len(cats), len(DEFAULT_CATEGORY_TEMPLATES))
        names = {c["name"] for c in cats}
        self.assertIn("流媒体", names)
        # 幂等：同一用户第二次调用不再写入。
        self.assertFalse(category_service.ensure_default_categories_for_user("u-1000"))
        self.assertEqual(len(category_service.list_categories("u-1000")), len(cats))

    def test_deleted_categories_not_resurrected(self):
        category_service.ensure_default_categories_for_user("u-2000")
        for cat in category_service.list_categories("u-2000"):
            category_service.delete_category(cat["id"], "u-2000")
        self.assertEqual(category_service.list_categories("u-2000"), [])
        category_service.ensure_default_categories_for_user("u-2000")
        self.assertEqual(category_service.list_categories("u-2000"), [])

    def test_empty_user_id_is_noop(self):
        self.assertFalse(category_service.ensure_default_categories_for_user(""))
        self.assertFalse(category_service.ensure_default_categories_for_user("  "))

    def test_local_seed_marked_on_fresh_db(self):
        # 全新库：'local' 分类在首次 API 请求（补种钩子）时写入。
        category_service.ensure_default_categories_for_user("local")
        self.assertGreater(len(category_service.list_categories("local")), 0)
        self.assertFalse(category_service.ensure_default_categories_for_user("local"))

    def test_upgrade_marks_existing_users(self):
        # 模拟 v11 迁移语义：已有数据的老用户被标记，首次请求不再补种。
        conn = sqlite3.connect(str(self.root / "test.db"))
        self.addCleanup(conn.close)
        conn.execute(
            "INSERT INTO subscriptions (id, user_id, name, amount, currency, "
            "period_type, start_date, created_at, updated_at) "
            "VALUES ('legacy-sub', 'legacy', '旧订阅', 1000, 'CNY', 'month', "
            "'2026-01-01', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO seeded_users (user_id, seeded_at) "
            "VALUES ('legacy', '2026-01-01T00:00:00Z')"
        )
        conn.commit()
        self.assertFalse(category_service.ensure_default_categories_for_user("legacy"))
        self.assertEqual(category_service.list_categories("legacy"), [])


class ReminderDaysSeedTests(unittest.TestCase):
    """安装向导提醒天数（seed_default_settings）落库行为。

    与 AppTestCase 不同：每个测试用独立数据库文件，并反复建/拆应用
    来模拟重装场景。
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls._old_overrides = dict(getattr(config, "_OVERRIDES", {}))
        config.override("WWW_DIR", str(cls.root / "www"))

    @classmethod
    def tearDownClass(cls):
        config.override("wizard_reminder_days", None)
        current_keys = set(getattr(config, "_OVERRIDES", {}))
        old_keys = set(cls._old_overrides)
        for key in current_keys | old_keys:
            config.override(key, cls._old_overrides.get(key))
        cls.tmp.cleanup()

    def _build_app(self, db_path: Path):
        from backend.app import create_app

        config.override("DB_PATH", str(db_path))
        app = create_app(allow_headerless_local_identity=True)
        app.config["TESTING"] = True
        return app

    def _dispose(self, app):
        with app.app_context():
            repositories.db.session.remove()
            repositories.db.engine.dispose()

    def _days(self):
        return repositories.get_app_settings()["notification_days"]

    def test_fresh_db_with_wizard_override(self):
        # 安装向导填 4 -> 全新库首行即为 4
        config.override("wizard_reminder_days", "4")
        app = self._build_app(self.root / "wizard.db")
        try:
            with app.app_context():
                self.assertEqual(self._days(), 4)
        finally:
            self._dispose(app)

    def test_fresh_db_without_override_defaults_to_7(self):
        # 清除前序测试残留的向导值，验证默认 7 天
        config.override("wizard_reminder_days", None)
        app = self._build_app(self.root / "default.db")
        try:
            with app.app_context():
                self.assertEqual(self._days(), 7)
        finally:
            self._dispose(app)

    def test_existing_value_upserted_by_wizard_override(self):
        # 模拟旧版残留 3 + 重装时向导再次传入 -> 应覆盖为 4
        config.override("wizard_reminder_days", None)
        app = self._build_app(self.root / "upsert.db")
        with app.app_context():
            repositories.update_app_settings({"notification_days": 3})
        self._dispose(app)
        config.override("wizard_reminder_days", "4")
        app2 = self._build_app(self.root / "upsert.db")
        try:
            with app2.app_context():
                self.assertEqual(self._days(), 4)
        finally:
            self._dispose(app2)

    def test_existing_value_preserved_without_override(self):
        # 升级/普通启动无向导值 -> 不得覆盖用户已有设置
        config.override("wizard_reminder_days", None)
        app = self._build_app(self.root / "preserve.db")
        with app.app_context():
            repositories.update_app_settings({"notification_days": 5})
        self._dispose(app)
        app2 = self._build_app(self.root / "preserve.db")
        try:
            with app2.app_context():
                self.assertEqual(self._days(), 5)
        finally:
            self._dispose(app2)


class ServicesTests(AppTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with cls.ctx():
            cat = category_service.create_category("u1", {"name": "流媒体"})
            sub_service.create_subscription(
                "u1",
                {
                    "name": "Netflix",
                    "amount": 6800,
                    "currency": "CNY",
                    "period_type": "month",
                    "auto_renew": True,
                    "start_date": "2026-06-11",
                    "next_due_date": "2026-08-15",
                    "category_id": cat["id"],
                },
            )
            sub_service.create_subscription(
                "u1",
                {
                    "name": "iCloud",
                    "amount": 2100,
                    "currency": "CNY",
                    "period_type": "year",
                    "auto_renew": True,
                    "start_date": "2026-05-01",
                    "next_due_date": "2026-09-01",
                },
            )

    def test_statistics_shape(self):
        stats = calculate_statistics("u1", "nominal")
        for key in (
            "monthly_expense",
            "monthly_actual_expense",
            "yearly_expense",
            "upcoming_30_days",
            "active_count",
            "category_stats",
            "monthly_trend",
        ):
            self.assertIn(key, stats)
        self.assertEqual(stats["active_count"], 2)
        self.assertEqual(len(stats["monthly_trend"]), 12)
        self.assertTrue(stats["monthly_expense"] > 0)
        # 验证月度趋势并不是每个月都相同
        trend_amounts = [m["amount"] for m in stats["monthly_trend"]]
        self.assertIsInstance(trend_amounts, list)

    def test_subscription_creation_creates_payment(self):
        sub = sub_service.create_subscription(
            "u_pay_test",
            {
                "name": "Apple Music",
                "amount": 1000,
                "currency": "CNY",
                "period_type": "month",
                "auto_renew": True,
                "start_date": "2026-01-01",
                "next_due_date": "2026-02-01",
            },
        )
        payments = repositories.get_payments_by_subscription(sub["id"])
        self.assertEqual(len(payments), 1)
        self.assertEqual(payments[0]["payment_type"], "first")
        self.assertEqual(payments[0]["amount"], 1000)
        self.assertEqual(payments[0]["currency"], "CNY")
        self.assertEqual(payments[0]["exchange_rate"], 1.0)
        self.assertEqual(payments[0]["amount_cny"], 1000)

    def test_payment_exchange_rate_snapshot_and_isolation(self):
        # 1. 创建美元订阅，生成第一笔按 7.2 汇率折算的支付记录
        sub = sub_service.create_subscription(
            "u_usd_test",
            {
                "name": "ChatGPT Plus",
                "amount": 2000,  # 20.00 USD
                "currency": "USD",
                "period_type": "month",
                "auto_renew": True,
                "start_date": "2026-01-01",
                "next_due_date": "2026-02-01",
            },
        )
        payments = repositories.get_payments_by_subscription(sub["id"])
        self.assertEqual(len(payments), 1)
        p1 = payments[0]
        self.assertEqual(p1["amount"], 2000)
        self.assertEqual(p1["currency"], "USD")
        self.assertAlmostEqual(p1["exchange_rate"], 7.2)
        self.assertEqual(p1["amount_cny"], round(2000 * 7.2))  # 14400

        # 2. 系统设置修改汇率（比如 USD 暴涨到 8.0）
        repositories.update_app_settings({"exchange_rate_usd": 8.0})

        # 3. 验证历史第一笔支付记录的 amount_cny 与 exchange_rate 快照完全不受影响
        p1_after = repositories.get_payments_by_subscription(sub["id"])[0]
        self.assertAlmostEqual(p1_after["exchange_rate"], 7.2)
        self.assertEqual(p1_after["amount_cny"], 14400)

        # 4. 再次续费，生成新支付流水，新流水使用新汇率 8.0
        sub_service.renew_subscription(sub["id"], "u_usd_test")
        payments_renewed = repositories.get_payments_by_subscription(sub["id"])
        self.assertEqual(len(payments_renewed), 2)
        p2 = [p for p in payments_renewed if p["payment_type"] == "renewal"][0]
        self.assertAlmostEqual(p2["exchange_rate"], 8.0)
        self.assertEqual(p2["amount_cny"], round(2000 * 8.0))  # 16000

    def test_renew_subscription_creates_renewal_payment(self):
        sub = sub_service.create_subscription(
            "u_renew_test",
            {
                "name": "Spotify",
                "amount": 1500,
                "currency": "CNY",
                "period_type": "month",
                "auto_renew": True,
                "start_date": "2026-01-01",
                "next_due_date": "2026-02-01",
            },
        )
        renewed = sub_service.renew_subscription(sub["id"], "u_renew_test")
        self.assertIsNotNone(renewed)
        payments = repositories.get_payments_by_subscription(sub["id"])
        self.assertEqual(len(payments), 2)
        types = [p["payment_type"] for p in payments]
        self.assertIn("first", types)
        self.assertIn("renewal", types)

    def test_soft_delete_preserves_payments_and_can_restore(self):
        user_id = "u_soft_del_test"
        sub = sub_service.create_subscription(
            user_id,
            {
                "name": "Netflix",
                "amount": 2500,
                "currency": "CNY",
                "period_type": "month",
                "auto_renew": True,
                "start_date": "2026-01-01",
                "next_due_date": "2026-02-01",
            },
        )
        sub_id = sub["id"]

        # 验证初始已生成支付流水
        payments_before = repositories.get_payments_by_subscription(sub_id)
        self.assertEqual(len(payments_before), 1)

        # 执行删除（软删除）
        deleted_ok = sub_service.delete_subscription(sub_id, user_id)
        self.assertTrue(deleted_ok)

        # 默认查询已查不到
        self.assertIsNone(sub_service.get_subscription(sub_id, user_id))
        all_subs = sub_service.list_subscriptions(user_id)
        self.assertNotIn(sub_id, [s["id"] for s in all_subs])

        # 核心保证：关联的 payments 流水依然完好无损！
        payments_after = repositories.get_payments_by_subscription(sub_id)
        self.assertEqual(len(payments_after), 1)
        self.assertEqual(payments_after[0]["amount"], 2500)

        # 软删除项不能被续费
        self.assertIsNone(sub_service.renew_subscription(sub_id, user_id))

        # 支持被恢复 (restore)
        restored = sub_service.restore_subscription(sub_id, user_id)
        self.assertIsNotNone(restored)
        self.assertIsNone(restored["deleted_at"])

        # 恢复后重新出现在正常列表中
        self.assertIsNotNone(sub_service.get_subscription(sub_id, user_id))
        restored_list = sub_service.list_subscriptions(user_id)
        self.assertIn(sub_id, [s["id"] for s in restored_list])

    def test_calendar_events(self):
        events = get_calendar_events("u1", 2026, 8)
        self.assertTrue(events)
        self.assertTrue(all(e["date"].startswith("2026-08") for e in events))


class StaticServeTests(AppTestCase):
    """静态文件 MIME 映射（Flask 版本使用 werkzeug 内置 MIME 检测）。"""

    def test_flask_static_mime_detection(self):
        """Flask/werkzeug 正确检测常见静态文件 MIME 类型。"""
        import mimetypes

        # werkzeug 使用 mimetypes 模块，验证常见类型
        self.assertEqual(mimetypes.guess_type("style.css")[0], "text/css")
        # Python 3.11+ 返回 text/javascript，旧版返回 application/javascript
        js_mime = mimetypes.guess_type("app.js")[0]
        self.assertIn(js_mime, ["application/javascript", "text/javascript"])
        self.assertEqual(mimetypes.guess_type("index.html")[0], "text/html")
        self.assertEqual(mimetypes.guess_type("image.png")[0], "image/png")
        # Windows/Python 版本差异：image/svg 或 image/svg+xml
        svg_mime = mimetypes.guess_type("icon.svg")[0]
        self.assertIn(svg_mime, ["image/svg", "image/svg+xml"])

    def test_flask_static_file_serving(self):
        """Flask 正确提供静态文件。"""
        import tempfile

        from backend.app import create_app
        from backend.extensions import db as _db

        with tempfile.TemporaryDirectory() as tmp:
            www = Path(tmp) / "www"
            www.mkdir()
            (www / "index.html").write_text("<h1>Hello</h1>", encoding="utf-8")
            (www / "style.css").write_text("body { color: red; }", encoding="utf-8")
            (www / "app.js").write_text("console.log('test')", encoding="utf-8")

            config.override("WWW_DIR", str(www))
            try:
                app = create_app(allow_headerless_local_identity=True)
                app.config["TESTING"] = True
                client = app.test_client()

                # 测试 HTML 文件（读取并关闭响应体，确保文件句柄释放）
                response = client.get("/index.html")
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response.content_type)
                response.get_data()
                response.close()

                # 测试 CSS 文件
                response = client.get("/style.css")
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/css", response.content_type)
                response.get_data()
                response.close()

                # 测试 JS 文件
                response = client.get("/app.js")
                self.assertEqual(response.status_code, 200)
                self.assertIn("javascript", response.content_type)
                response.get_data()
                response.close()
            finally:
                config.override("WWW_DIR", None)
                with app.app_context():
                    _db.session.remove()
                    _db.engine.dispose()


class LogTailTests(unittest.TestCase):
    """运行日志尾读（api/logs 模块）。"""

    def test_read_tail_lines_and_missing_file(self):
        from backend.api.logs import _read_log_tail

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "app.log"
            p.write_text("".join(f"line{i}\n" for i in range(1, 101)), encoding="utf-8")

            # 取 1 行 -> 最后一行；取 5/200 行 -> 截到文件长度
            r1 = _read_log_tail(p, 1)
            self.assertEqual(r1["lines"], ["line100"])
            self.assertIsNone(r1["error"])
            self.assertEqual(len(_read_log_tail(p, 5)["lines"]), 5)
            self.assertEqual(len(_read_log_tail(p, 200)["lines"]), 100)

            # 文件不存在 -> 空列表且无错误
            missing = _read_log_tail(Path(tmp) / "nope.log", 10)
            self.assertEqual(missing["lines"], [])
            self.assertIsNone(missing["error"])

    def test_cleanup_old_logs(self):
        from backend import server

        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            old = d / "app.log.3"
            old.write_text("old", encoding="utf-8")
            # 把 mtime 改为很久以前
            old_ts = time.time() - (server._LOG_RETENTION_DAYS + 10) * 86400
            os.utime(old, (old_ts, old_ts))
            fresh = d / "app.log"
            fresh.write_text("fresh", encoding="utf-8")
            unrelated = d / "other.txt"
            unrelated.write_text("keep", encoding="utf-8")

            server._cleanup_old_logs(d)

            self.assertFalse(old.exists(), "过期轮转日志应被清理")
            self.assertTrue(fresh.exists(), "新日志保留")
            self.assertTrue(unrelated.exists(), "非日志文件不动")


if __name__ == "__main__":
    unittest.main()
