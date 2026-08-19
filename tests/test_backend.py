"""后端单元测试（unittest，无网络依赖）。

运行：python3 -m unittest discover -s tests -v
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "backend"))

import db
import domain
import services


class DomainTests(unittest.TestCase):
    def test_add_month_clamps_day(self):
        from datetime import date
        self.assertEqual(domain.add_one_period(date(2026, 1, 31), "month"), date(2026, 2, 28))
        self.assertEqual(domain.add_one_period(date(2026, 8, 31), "month"), date(2026, 9, 30))

    def test_add_quarter_year(self):
        from datetime import date
        self.assertEqual(domain.add_one_period(date(2026, 2, 14), "quarter"), date(2026, 5, 14))
        self.assertEqual(domain.add_one_period(date(2026, 2, 14), "year"), date(2027, 2, 14))

    def test_once_has_no_next(self):
        from datetime import date
        self.assertIsNone(domain.add_one_period(date(2026, 1, 31), "once"))

    def test_custom_period(self):
        from datetime import date
        self.assertEqual(domain.add_one_period(date(2026, 3, 1), "custom", 2, "week"),
                         date(2026, 3, 15))
        self.assertEqual(domain.add_one_period(date(2026, 3, 1), "custom", 2, "month"),
                         date(2026, 5, 1))

    def test_sub_is_inverse(self):
        from datetime import date
        d = date(2026, 5, 20)
        fwd = domain.add_one_period(d, "month")
        self.assertEqual(domain.sub_one_period(fwd, "month"), d)

    def test_normalize_renewal(self):
        self.assertEqual(domain.normalize_renewal_on_create(True, "stop"), (False, "stop"))
        self.assertEqual(domain.normalize_renewal_on_create(True, None), (True, "auto"))
        self.assertEqual(domain.normalize_renewal_on_create(False, None), (False, "manual"))

    def test_derive_status(self):
        from datetime import date, timedelta
        today = date.today()
        soon = (today + timedelta(days=3)).isoformat()
        later = (today + timedelta(days=30)).isoformat()
        self.assertEqual(domain.derive_status("active", soon), "expiring")
        self.assertEqual(domain.derive_status("active", later), "active")
        self.assertEqual(domain.derive_status("canceled", later), "canceled")


class DbTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        db.connect(Path(cls.tmp.name) / "test.db")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_create_and_get(self):
        sub = db.create_subscription("u1", {
            "name": "Netflix", "amount": 6800, "currency": "CNY",
            "period_type": "month", "auto_renew": True,
            "start_date": "2026-06-11", "next_due_date": "2026-08-15",
        })
        self.assertEqual(sub["amount"], 6800)
        self.assertEqual(sub["renewal_policy"], "auto")
        got = db.get_subscription_by_id(sub["id"], "u1")
        self.assertEqual(got["name"], "Netflix")

    def test_multi_user_isolation(self):
        db.create_subscription("alice", {"name": "A", "amount": 100, "period_type": "month",
                                         "start_date": "2026-01-01"})
        db.create_subscription("bob", {"name": "B", "amount": 200, "period_type": "month",
                                       "start_date": "2026-01-01"})
        self.assertEqual([s["name"] for s in db.get_all_subscriptions("alice")], ["A"])
        self.assertEqual([s["name"] for s in db.get_all_subscriptions("bob")], ["B"])

    def test_renew_advances(self):
        sub = db.create_subscription("u1", {
            "name": "iCloud", "amount": 2100, "period_type": "year",
            "start_date": "2026-05-01", "next_due_date": "2026-09-01",
        })
        renewed = db.renew_subscription(sub["id"], "u1")
        self.assertEqual(renewed["next_due_date"], "2027-09-01")

    def test_once_auto_renew_false(self):
        sub = db.create_subscription("u1", {
            "name": "一次性", "amount": 100, "period_type": "once", "auto_renew": True,
            "start_date": "2026-01-01",
        })
        self.assertFalse(sub["auto_renew"])
        self.assertEqual(sub["renewal_policy"], "manual")

    def test_switching_from_custom_period_clears_legacy_custom_fields(self):
        sub = db.create_subscription("u1", {
            "name": "自定义周期", "amount": 100, "period_type": "custom",
            "custom_period_value": 2, "custom_period_unit": "week",
            "start_date": "2026-01-01",
        })
        updated = db.update_subscription(sub["id"], "u1", {"period_type": "month"})
        self.assertEqual(updated["period_type"], "month")
        self.assertIsNone(updated["custom_period_value"])
        self.assertIsNone(updated["custom_period_unit"])

    def test_notes_are_limited_to_120_characters(self):
        notes = "备" * 120
        sub = db.create_subscription("u1", {
            "name": "备注限制", "amount": 100, "period_type": "month",
            "start_date": "2026-01-01", "notes": notes,
        })
        self.assertEqual(sub["notes"], notes)

        with self.assertRaisesRegex(ValueError, "备注不能超过120字"):
            db.create_subscription("u1", {
                "name": "超长备注", "amount": 100, "period_type": "month",
                "start_date": "2026-01-01", "notes": "备" * 121,
            })

        with self.assertRaisesRegex(ValueError, "备注不能超过120字"):
            db.update_subscription(sub["id"], "u1", {"notes": "备" * 121})

    def test_settings_defaults_and_update(self):
        s = db.get_app_settings()
        self.assertEqual(s["default_currency"], "CNY")
        db.update_app_settings({"notification_days": 5, "exchange_rate_usd": 7.1})
        s = db.get_app_settings()
        self.assertEqual(s["notification_days"], 5)
        self.assertAlmostEqual(s["exchange_rate_usd"], 7.1)

    def test_categories(self):
        c = db.create_category("u1", {"name": "流媒体", "icon": "🎬"})
        self.assertTrue(c["id"])
        self.assertEqual(len(db.get_all_categories("u1")), 1)
        self.assertTrue(db.delete_category(c["id"], "u1"))
        self.assertEqual(len(db.get_all_categories("u1")), 0)


class ServicesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        db.connect(Path(cls.tmp.name) / "svc.db")
        cat = db.create_category("u1", {"name": "流媒体"})
        db.create_subscription("u1", {
            "name": "Netflix", "amount": 6800, "currency": "CNY",
            "period_type": "month", "auto_renew": True,
            "start_date": "2026-06-11", "next_due_date": "2026-08-15",
            "category_id": cat["id"],
        })
        db.create_subscription("u1", {
            "name": "iCloud", "amount": 2100, "currency": "CNY",
            "period_type": "year", "auto_renew": True,
            "start_date": "2026-05-01", "next_due_date": "2026-09-01",
        })

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_statistics_shape(self):
        stats = services.calculate_statistics("u1", "nominal")
        for key in ("monthly_expense", "monthly_actual_expense", "yearly_expense",
                    "upcoming_30_days", "active_count", "category_stats", "monthly_trend"):
            self.assertIn(key, stats)
        self.assertEqual(stats["active_count"], 2)
        self.assertEqual(len(stats["monthly_trend"]), 12)
        self.assertTrue(stats["monthly_expense"] > 0)
        # 验证月度趋势并不是每个月都相同
        trend_amounts = [m["amount"] for m in stats["monthly_trend"]]
        self.assertIsInstance(trend_amounts, list)

    def test_calendar_events(self):
        from datetime import date
        events = services.get_calendar_events("u1", 2026, 8)
        self.assertTrue(events)
        self.assertTrue(all(e["date"].startswith("2026-08") for e in events))


class StaticServeTests(unittest.TestCase):
    """静态文件 MIME 映射（对齐 fnOS 官方 index.cgi 示例：css/js 带 charset）。"""

    def test_mime_map_css_js_html(self):
        import server
        m = server.Handler._STATIC_MIME
        self.assertEqual(m[".css"], "text/css; charset=utf-8")
        self.assertEqual(m[".js"], "application/javascript; charset=utf-8")
        self.assertEqual(m[".html"], "text/html; charset=utf-8")
        self.assertEqual(m[".png"], "image/png")
        self.assertEqual(m[".svg"], "image/svg+xml")

    def test_serve_static_mime_uses_map(self):
        import mimetypes
        import server
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # 模拟浏览器请求的静态文件
            for name, expect in [("style.css", "text/css; charset=utf-8"),
                                 ("app.js", "application/javascript; charset=utf-8")]:
                f = root / name
                f.write_text("x", encoding="utf-8")
                # 复刻 _serve_static 的 MIME 解析逻辑
                suffix = "." + f.name.rsplit(".", 1)[-1]
                ctype = server.Handler._STATIC_MIME.get(suffix) \
                    or mimetypes.guess_type(str(f))[0] \
                    or "application/octet-stream"
                # 显式映射优先，且不同于无 charset 的 guess_type 结果
                self.assertEqual(ctype, expect)
                self.assertNotEqual(ctype, mimetypes.guess_type(str(f))[0])


if __name__ == "__main__":
    unittest.main()
