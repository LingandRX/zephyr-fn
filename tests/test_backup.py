"""备份导出/导入的范围和 CSV 往返回归测试。"""
from __future__ import annotations

import unittest

from helpers import AppTestCase
from backend.services import backup
from backend.services import subscriptions as sub_service


class BackupRoundTripTests(AppTestCase):
    def test_csv_round_trip_preserves_start_date_and_custom_period(self):
        original = sub_service.create_subscription(
            "alice",
            {
                "name": "Custom service",
                "amount": 1234,
                "period_type": "custom",
                "custom_period_value": 2,
                "custom_period_unit": "week",
                "start_date": "2026-01-31",
                "first_payment_date": None,
            },
        )

        exported = backup.export_csv("alice")
        self.assertIn("开始日期", exported)
        self.assertIn("自定义周期单位", exported)

        result = backup.import_from_csv(exported, "bob")
        self.assertEqual(result["success_count"], 1)
        imported = sub_service.list_subscriptions("bob")
        self.assertEqual(len(imported), 1)
        self.assertNotEqual(imported[0]["id"], original["id"])
        self.assertEqual(imported[0]["start_date"], "2026-01-31")
        self.assertEqual(imported[0]["period_type"], "custom")
        self.assertEqual(imported[0]["custom_period_value"], 2)
        self.assertEqual(imported[0]["custom_period_unit"], "week")

    def test_export_requires_explicit_scope(self):
        with self.assertRaises(ValueError):
            backup.export_json_string()
        with self.assertRaises(ValueError):
            backup.export_csv()


if __name__ == "__main__":
    unittest.main()
