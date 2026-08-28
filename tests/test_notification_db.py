"""notification_logs 迁移、唯一约束和幂等发送测试。

旧库升级路径（bootstrap）测试：先在全新库上模拟旧版本状态
（回退 db_version、删除 v9/v10 索引、插入重复数据），
再调用 bootstrap.bootstrap_legacy_database() 验证就地迁移行为。
"""
from __future__ import annotations

import sqlite3
import unittest
from datetime import date

from helpers import AppTestCase
from backend.extensions import db
from backend.services import notifications
from backend.storage import bootstrap, repositories


class NotificationDbTests(AppTestCase):
    def setUp(self):
        super().setUp()
        # 每个测试从干净的通知表开始（类级共享数据库）
        from sqlalchemy import text
        db.session.execute(text("DELETE FROM notification_logs"))
        db.session.commit()

    def _raw(self):
        """打开原始 sqlite3 连接（Row 工厂），测试结束时自动关闭。"""
        conn = sqlite3.connect(str(self.root / "test.db"))
        conn.row_factory = sqlite3.Row
        self.addCleanup(conn.close)
        return conn

    def _rows(self):
        return self._raw().execute(
            "SELECT * FROM notification_logs ORDER BY subscription_id, channel"
        ).fetchall()

    def _version(self):
        raw = self._raw()
        row = raw.execute("SELECT version FROM db_version WHERE id=1").fetchone()
        return int(row[0]) if row else None

    def _simulate_legacy(self, version: int) -> None:
        """把库回退到指定旧版本：补 db_version 表 + 回退版本号。"""
        raw = self._raw()
        raw.execute("CREATE TABLE IF NOT EXISTS db_version "
                    "(id INTEGER PRIMARY KEY CHECK (id=1), version INTEGER NOT NULL)")
        raw.execute("INSERT OR REPLACE INTO db_version (id, version) VALUES (1, ?)",
                    (version,))
        raw.commit()

    def test_v9_upgrade_deduplicates_before_creating_unique_index(self):
        today = date.today().isoformat()

        # 模拟 v8 旧库：删除 v9 唯一索引、回退版本号、插入重复通知，
        # 然后触发旧库就地升级（bootstrap），验证真实 v8 -> v9 迁移。
        raw = self._raw()
        raw.execute("DROP INDEX idx_notification_logs_identity")
        self._simulate_legacy(8)
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

        with self.ctx():
            self.assertTrue(bootstrap.bootstrap_legacy_database())

        rows = self._rows()
        self.assertEqual(self._version(), bootstrap.CURRENT_LEGACY_DB_VERSION)
        self.assertEqual(len(rows), 2)
        by_key = {(row["subscription_id"], row["channel"]): row for row in rows}
        self.assertEqual(by_key[("sub-a", "email")]["id"], "sent-old")
        self.assertEqual(by_key[("sub-a", "email")]["status"], "sent")
        self.assertEqual(by_key[("sub-b", "push")]["id"], "failed-new-2")

        raw = self._raw()
        indexes = raw.execute("PRAGMA index_list(notification_logs)").fetchall()
        identity_index = next(
            index for index in indexes
            if index[1] == "idx_notification_logs_identity"
        )
        self.assertTrue(identity_index[2])
        columns = [row[2] for row in raw.execute(
            'PRAGMA index_info("idx_notification_logs_identity")'
        ).fetchall()]
        self.assertEqual(columns, ["subscription_id", "notification_date", "channel"])

    def test_log_notification_is_single_row_upsert_and_sent_is_terminal(self):
        repositories.log_notification("sub", "email", "failed", "first")
        repositories.log_notification("sub", "email", "failed", "second")
        self.assertEqual(len(self._rows()), 1)
        self.assertEqual(self._rows()[0]["error_message"], "second")

        repositories.log_notification("sub", "email", "sent")
        repositories.log_notification("sub", "email", "sent")
        repositories.log_notification("sub", "email", "failed", "late failure")
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "sent")
        self.assertTrue(repositories.has_channel_notified_today("sub", "email"))

    def test_claim_reuses_failed_and_expired_rows_without_conflict(self):
        repositories.log_notification("sub", "email", "failed", "send failed")
        claim_id = notifications.claim_notification("sub", "email")
        self.assertIsNotNone(claim_id)
        self.assertFalse(str(claim_id).startswith(("memory:", "legacy:")))
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], claim_id)
        self.assertEqual(rows[0]["status"], "pending")

        notifications.complete_notification(claim_id, "sub", "email", "failed", "retry")
        retry_id = notifications.claim_notification("sub", "email")
        self.assertIsNotNone(retry_id)
        self.assertEqual(len(self._rows()), 1)

        # 模拟旧领取者超时：expired -> pending 仍走 UPSERT，不新增 identity 行。
        repositories.log_notification("expired", "push", "pending")
        raw = self._raw()
        raw.execute(
            "UPDATE notification_logs SET created_at=? WHERE subscription_id=?",
            ("2026-08-01T00:00:00Z", "expired"),
        )
        raw.commit()
        expired_claim = notifications.claim_notification("expired", "push")
        self.assertIsNotNone(expired_claim)
        expired_rows = [row for row in self._rows() if row["subscription_id"] == "expired"]
        self.assertEqual(len(expired_rows), 1)
        self.assertEqual(expired_rows[0]["status"], "pending")

        notifications.complete_notification(retry_id, "sub", "email", "sent")
        notifications.complete_notification(expired_claim, "expired", "push", "sent")
        self.assertTrue(repositories.has_channel_notified_today("sub", "email"))
        self.assertTrue(repositories.has_channel_notified_today("expired", "push"))

    def test_v10_upgrade_deduplicates_and_merges_subscriptions(self):
        # 模拟 v9 旧库：删除 v10 索引并回退版本号，插入大小写/全角重复分类
        # 以及引用这些分类的订阅，验证迁移会归一化去重并归并订阅引用。
        raw = self._raw()
        raw.execute("DROP INDEX IF EXISTS idx_cat_user_name")
        raw.execute("DROP INDEX IF EXISTS idx_cat_user_sort")
        self._simulate_legacy(9)
        raw.execute("DELETE FROM subscriptions")
        raw.execute("DELETE FROM categories")
        raw.executemany(
            "INSERT INTO categories (id, user_id, name, icon, sort_order) "
            "VALUES (?,?,?,?,?)",
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

        with self.ctx():
            self.assertTrue(bootstrap.bootstrap_legacy_database())
        self.assertEqual(self._version(), bootstrap.CURRENT_LEGACY_DB_VERSION)

        raw = self._raw()
        cats = raw.execute("SELECT id, name FROM categories ORDER BY rowid").fetchall()
        self.assertEqual(
            [dict(row) for row in cats],
            [{"id": "cat-a", "name": "Stream"}, {"id": "cat-d", "name": "Games"}],
        )

        merged = raw.execute(
            "SELECT id, category_id FROM subscriptions ORDER BY id"
        ).fetchall()
        self.assertEqual(
            [dict(row) for row in merged],
            [
                {"id": "sub-1", "category_id": "cat-a"},
                {"id": "sub-2", "category_id": "cat-a"},
                {"id": "sub-3", "category_id": "cat-d"},
            ],
        )

        indexes = raw.execute("PRAGMA index_list(categories)").fetchall()
        names = [i[1] for i in indexes]
        self.assertIn("idx_cat_user_name", names)
        self.assertIn("idx_cat_user_sort", names)
        uniq = next(i for i in indexes if i[1] == "idx_cat_user_name")
        self.assertTrue(uniq[2])


if __name__ == "__main__":
    unittest.main()
