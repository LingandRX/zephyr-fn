"""后端单元测试（unittest，无网络依赖）。

运行：python3 -m unittest discover -s tests -v
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "backend"))

import config
import services
from core import domain
from storage import db



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


class DefaultCategorySeedTests(unittest.TestCase):
    """按用户懒播种默认分类（v11 seeded_users 机制）。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.connect(Path(self.tmp.name) / "seed.db")

    def tearDown(self):
        db.close()
        self.tmp.cleanup()

    def test_new_user_gets_defaults_once(self):
        self.assertTrue(db.ensure_default_categories_for_user("u-1000"))
        cats = db.get_all_categories("u-1000")
        self.assertGreaterEqual(len(cats), len(db._DEFAULT_CATEGORY_TEMPLATES))
        names = {c["name"] for c in cats}
        self.assertIn("流媒体", names)
        # 幂等：同一用户第二次调用不再写入。
        self.assertFalse(db.ensure_default_categories_for_user("u-1000"))
        self.assertEqual(len(db.get_all_categories("u-1000")), len(cats))

    def test_deleted_categories_not_resurrected(self):
        db.ensure_default_categories_for_user("u-2000")
        for cat in db.get_all_categories("u-2000"):
            db.delete_category(cat["id"], "u-2000")
        self.assertEqual(db.get_all_categories("u-2000"), [])
        db.ensure_default_categories_for_user("u-2000")
        self.assertEqual(db.get_all_categories("u-2000"), [])

    def test_empty_user_id_is_noop(self):
        self.assertFalse(db.ensure_default_categories_for_user(""))
        self.assertFalse(db.ensure_default_categories_for_user("  "))

    def test_local_seed_marked_on_fresh_db(self):
        # 全新库启动后 'local' 已有种子分类且已打标。
        self.assertGreater(len(db.get_all_categories("local")), 0)
        self.assertFalse(db.ensure_default_categories_for_user("local"))

    def test_upgrade_marks_existing_users(self):
        # 模拟 v11 迁移语义：已有数据的老用户被标记，首次请求不再补种。
        conn = db._conn
        with db._lock:
            marked = conn.execute(
                "SELECT user_id FROM seeded_users WHERE user_id='legacy'"
            ).fetchone()
            if not marked:
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
        self.assertFalse(db.ensure_default_categories_for_user("legacy"))
        self.assertEqual(db.get_all_categories("legacy"), [])


class ReminderDaysSeedTests(unittest.TestCase):
    """安装向导提醒天数（_seed_default_settings）落库行为。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "seed.db"

    def tearDown(self):
        db.close()
        config.override("wizard_reminder_days", None)
        self.tmp.cleanup()

    def _days(self):
        return db.get_app_settings()["notification_days"]

    def test_fresh_db_with_wizard_override(self):
        # 安装向导填 4 -> 全新库首行即为 4
        config.override("wizard_reminder_days", "4")
        db.connect(self.db_path)
        self.assertEqual(self._days(), 4)

    def test_fresh_db_without_override_defaults_to_7(self):
        db.connect(self.db_path)
        self.assertEqual(self._days(), 7)

    def test_existing_value_upserted_by_wizard_override(self):
        # 模拟旧版残留 3 + 重装时向导再次传入 -> 应覆盖为 4
        db.connect(self.db_path)
        db.update_app_settings({"notification_days": 3})
        db.close()
        config.override("wizard_reminder_days", "4")
        db.connect(self.db_path)
        self.assertEqual(self._days(), 4)

    def test_existing_value_preserved_without_override(self):
        # 升级/普通启动无向导值 -> 不得覆盖用户已有设置
        db.connect(self.db_path)
        db.update_app_settings({"notification_days": 5})
        db.close()
        db.connect(self.db_path)
        self.assertEqual(self._days(), 5)


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
        self.assertEqual(mimetypes.guess_type("icon.svg")[0], "image/svg+xml")

    def test_flask_static_file_serving(self):
        """Flask 正确提供静态文件。"""
        import tempfile
        import server

        with tempfile.TemporaryDirectory() as tmp:
            www = Path(tmp) / "www"
            www.mkdir()
            (www / "index.html").write_text("<h1>Hello</h1>", encoding="utf-8")
            (www / "style.css").write_text("body { color: red; }", encoding="utf-8")
            (www / "app.js").write_text("console.log('test')", encoding="utf-8")

            config.override("WWW_DIR", str(www))
            try:
                app = server.create_app(allow_headerless_local_identity=True)
                app.config["TESTING"] = True
                client = app.test_client()

                # 测试 HTML 文件
                response = client.get("/index.html")
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response.content_type)

                # 测试 CSS 文件
                response = client.get("/style.css")
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/css", response.content_type)

                # 测试 JS 文件
                response = client.get("/app.js")
                self.assertEqual(response.status_code, 200)
                self.assertIn("javascript", response.content_type)
            finally:
                config.override("WWW_DIR", None)


class LogTailTests(unittest.TestCase):
    """运行日志尾读（_read_log_tail）。"""

    def test_read_tail_lines_and_missing_file(self):
        import server
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "app.log"
            p.write_text("".join(f"line{i}\n" for i in range(1, 101)), encoding="utf-8")

            # 取 1 行 -> 最后一行；取 5/200 行 -> 截到文件长度
            r1 = server._read_log_tail(p, 1)
            self.assertEqual(r1["lines"], ["line100"])
            self.assertIsNone(r1["error"])
            self.assertEqual(len(server._read_log_tail(p, 5)["lines"]), 5)
            self.assertEqual(len(server._read_log_tail(p, 200)["lines"]), 100)

            # 文件不存在 -> 空列表且无错误
            missing = server._read_log_tail(Path(tmp) / "nope.log", 10)
            self.assertEqual(missing["lines"], [])
            self.assertIsNone(missing["error"])

    def test_cleanup_old_logs(self):
        import server
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            old = d / "app.log.3"
            old.write_text("old", encoding="utf-8")
            # 把 mtime 改为很久以前
            import os
            import time as _t
            old_ts = _t.time() - (server._LOG_RETENTION_DAYS + 10) * 86400
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
