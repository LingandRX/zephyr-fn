"""备份导出/导入的范围和 CSV 往返回归测试。"""
from __future__ import annotations

import unittest

from helpers import AppTestCase
from backend.services import backup
from backend.services import subscriptions as sub_service


class CsvDownloadHeadersTests(AppTestCase):
    """CSV 下载响应头回归测试。

    回归背景：此前 endpoints 以 ``mimetype="text/csv; charset=utf-8"`` 构造响应，
    导致 Content-Type 变成 ``text/csv; charset=utf-8; charset=utf-8``（重复 charset），
    且 export/csv 缺少 Content-Disposition。Chrome 在识别这类畸形下载响应时失败，
    报“无法在网站提取文件”。本次修复必须保持下列头行为。
    """

    def setUp(self):
        super().setUp()
        self.client = self.app.test_client()
        self.admin_headers = {
            "X-Trim-Userid": "admin",
            "X-Trim-Isadmin": "true",
        }

    def test_export_csv_download_headers(self):
        res = self.client.get("/api/export/csv", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            res.headers["Content-Type"], "text/csv; charset=utf-8"
        )
        self.assertEqual(res.headers["Content-Type"].count("charset"), 1)
        disposition = res.headers["Content-Disposition"]
        self.assertIn("attachment", disposition)
        self.assertIn("subscriptions.csv", disposition)
        self.assertIn("filename*=", disposition)
        self.assertEqual(res.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(
            res.headers["Content-Length"], str(len(res.get_data()))
        )

    def test_import_template_download_headers(self):
        res = self.client.get("/api/backup/import-template", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            res.headers["Content-Type"], "text/csv; charset=utf-8"
        )
        self.assertEqual(res.headers["Content-Type"].count("charset"), 1)
        disposition = res.headers["Content-Disposition"]
        self.assertIn("attachment", disposition)
        self.assertIn("import_template.csv", disposition)
        self.assertIn("filename*=", disposition)
        self.assertEqual(res.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(
            res.headers["Content-Length"], str(len(res.get_data()))
        )
        self.assertIn("名称", res.get_data(as_text=True))

    def test_import_template_requires_admin(self):
        res = self.client.get(
            "/api/backup/import-template",
            headers={"X-Trim-Userid": "alice", "X-Trim-Isadmin": "false"},
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.get_json()["code"], 403)


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
            backup.export_csv()


if __name__ == "__main__":
    unittest.main()
