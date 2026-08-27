"""notification_logs 迁移、唯一约束和幂等发送测试。"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "backend"))

from services import notifications
from storage import db



class NotificationDbTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "notifications.db"
        db.connect(self.path)
        notifications._memory_claims.clear()

    def tearDown(self):
        notifications._memory_claims.clear()
        db.close()
        self.tmp.cleanup()

    def _rows(self):
        return db._conn.execute(  # noqa: SLF001 - test verifies DB-level behavior.
            "SELECT * FROM notification_logs ORDER BY subscription_id, channel"
        ).fetchall()

    def test_v9_upgrade_deduplicates_before_creating_unique_index(self):
        today = date.today().isoformat()
        db.close()

        # 先用当前 schema 建出 v9 数据库，再模拟 v8 旧库：删除 v9 索引并回退版本号，
        # 这样测试真实的 v8 -> v9 迁移，而不是只测试启动时自修复。
        raw = sqlite3.connect(self.path)
        raw.execute("DROP INDEX idx_notification_logs_identity")
        raw.execute("DROP TRIGGER IF EXISTS trg_notification_logs_reuse_failed")
        raw.execute("UPDATE db_version SET version=8 WHERE id=1")
        raw.execute("DELETE FROM notification_logs")
        raw.executemany(
            "INSERT INTO notification_logs "
            "(id, subscription_id, notification_date, channel, status, error_message, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            [
                # sent 即使较旧，也应胜过 failed。
                ("sent-old", "sub-a", today, "email", "sent", None,
                 "2026-08-01T00:00:00Z"),
                ("failed-new", "sub-a", today, "email", "failed", "late failure",
                 "2026-08-18T00:00:00Z"),
                # 同为 failed 时保留最新记录。
                ("failed-old", "sub-b", today, "push", "failed", "old failure",
                 "2026-08-01T00:00:00Z"),
                ("failed-new-2", "sub-b", today, "push", "failed", "new failure",
                 "2026-08-18T00:00:00Z"),
            ],
        )
        raw.commit()
        raw.close()

        db.connect(self.path)
        rows = self._rows()
        self.assertEqual(db._get_db_version(), db.CURRENT_DB_VERSION)  # noqa: SLF001
        self.assertEqual(len(rows), 2)
        by_key = {(row["subscription_id"], row["channel"]): row for row in rows}
        self.assertEqual(by_key[("sub-a", "email")]["id"], "sent-old")
        self.assertEqual(by_key[("sub-a", "email")]["status"], "sent")
        self.assertEqual(by_key[("sub-b", "push")]["id"], "failed-new-2")

        indexes = db._conn.execute("PRAGMA index_list(notification_logs)").fetchall()  # noqa: SLF001
        identity_index = next(
            index for index in indexes if index["name"] == "idx_notification_logs_identity"
        )
        self.assertTrue(identity_index["unique"])
        columns = [row[2] for row in db._conn.execute(  # noqa: SLF001
            'PRAGMA index_info("idx_notification_logs_identity")'
        ).fetchall()]
        self.assertEqual(columns, ["subscription_id", "notification_date", "channel"])

    def test_log_notification_is_single_row_upsert_and_sent_is_terminal(self):
        db.log_notification("sub", "email", "failed", "first")
        db.log_notification("sub", "email", "failed", "second")
        self.assertEqual(len(self._rows()), 1)
        self.assertEqual(self._rows()[0]["error_message"], "second")

        db.log_notification("sub", "email", "sent")
        db.log_notification("sub", "email", "sent")
        db.log_notification("sub", "email", "failed", "late failure")
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "sent")
        self.assertTrue(db.has_channel_notified_today("sub", "email"))

    def test_claim_reuses_failed_and_expired_rows_without_conflict(self):
        db.log_notification("sub", "email", "failed", "send failed")
        claim_id = notifications.claim_notification("sub", "email")
        self.assertIsNotNone(claim_id)
        self.assertFalse(str(claim_id).startswith("memory:"))
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], claim_id)
        self.assertEqual(rows[0]["status"], "pending")

        notifications.complete_notification(claim_id, "sub", "email", "failed", "retry")
        retry_id = notifications.claim_notification("sub", "email")
        self.assertIsNotNone(retry_id)
        self.assertEqual(len(self._rows()), 1)

        # 模拟旧领取者超时：expired -> failed -> pending 仍走 UPSERT，不新增 identity 行。
        db.log_notification("expired", "push", "pending")
        db._conn.execute(  # noqa: SLF001
            "UPDATE notification_logs SET created_at=? WHERE subscription_id=?",
            ("2026-08-01T00:00:00Z", "expired"),
        )
        db._conn.commit()  # noqa: SLF001
        expired_claim = notifications.claim_notification("expired", "push")
        self.assertIsNotNone(expired_claim)
        expired_rows = [row for row in self._rows() if row["subscription_id"] == "expired"]
        self.assertEqual(len(expired_rows), 1)
        self.assertEqual(expired_rows[0]["status"], "pending")

        notifications.complete_notification(retry_id, "sub", "email", "sent")
        notifications.complete_notification(expired_claim, "expired", "push", "sent")
        self.assertTrue(db.has_channel_notified_today("sub", "email"))
        self.assertTrue(db.has_channel_notified_today("expired", "push"))



    def test_v10_upgrade_deduplicates_and_merges_subscriptions(self):
        db.close()

        # 模拟 v9 旧库：删除 v10 索引并回退版本号，插入大小写/全角重复分类
        # 以及引用这些分类的订阅，验证迁移会归一化去重并归并订阅引用。
        raw = sqlite3.connect(self.path)
        raw.execute("DROP INDEX IF EXISTS idx_cat_user_name")
        raw.execute("DROP INDEX IF EXISTS idx_cat_user_sort")
        raw.execute("UPDATE db_version SET version=9 WHERE id=1")
        raw.execute("DELETE FROM subscriptions")
        raw.execute("DELETE FROM categories")
        raw.executemany(
            "INSERT INTO categories (id, user_id, name, icon, sort_order) VALUES (?,?,?,?,?)",
            [
                ("cat-a", "u1", "Stream", None, 0),       # 保留（rowid 最小）
                ("cat-b", "u1", "stream", None, 1),       # ASCII 大小写重复 -> 删除
                ("cat-c", "u1", "Ｓｔｒｅａｍ", None, 2),  # 全角重复 -> 删除
                ("cat-d", "u2", "Games", None, 0),
            ],
        )
        raw.executemany(
            "INSERT INTO subscriptions "
            "(id, user_id, name, amount, currency, category_id, period_type, start_date, "
            "lifecycle, renewal_policy, billing_status, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("sub-1", "u1", "Netflix", 100, "CNY", "cat-b", "month", "2026-01-01",
                 "active", "auto", "normal", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
                ("sub-2", "u1", "Spotify", 50, "CNY", "cat-c", "month", "2026-01-01",
                 "active", "auto", "normal", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
                ("sub-3", "u2", "Steam", 30, "CNY", "cat-d", "month", "2026-01-01",
                 "active", "auto", "normal", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
            ],
        )
        raw.commit()
        raw.close()

        db.connect(self.path)
        self.assertEqual(db._get_db_version(), db.CURRENT_DB_VERSION)  # noqa: SLF001

        cats = db._conn.execute(  # noqa: SLF001
            "SELECT id, name FROM categories ORDER BY rowid"
        ).fetchall()
        self.assertEqual(
            [dict(r) for r in cats],
            [{"id": "cat-a", "name": "Stream"}, {"id": "cat-d", "name": "Games"}],
        )

        merged = db._conn.execute(  # noqa: SLF001
            "SELECT id, category_id FROM subscriptions ORDER BY id"
        ).fetchall()
        self.assertEqual(
            [dict(r) for r in merged],
            [
                {"id": "sub-1", "category_id": "cat-a"},
                {"id": "sub-2", "category_id": "cat-a"},
                {"id": "sub-3", "category_id": "cat-d"},
            ],
        )

        indexes = db._conn.execute("PRAGMA index_list(categories)").fetchall()  # noqa: SLF001
        names = [i["name"] for i in indexes]
        self.assertIn("idx_cat_user_name", names)
        self.assertIn("idx_cat_user_sort", names)
        uniq = next(i for i in indexes if i["name"] == "idx_cat_user_name")
        self.assertTrue(uniq["unique"])

if __name__ == "__main__":
    unittest.main()
