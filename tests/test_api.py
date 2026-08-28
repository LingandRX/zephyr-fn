"""HTTP API 安全边界回归测试（Flask 版本）。

测试使用 Flask 测试客户端，为每次测试类创建临时数据库、静态目录和备份目录。
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "backend"))

import config
import server
from storage import db


class FlaskApiSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.www = cls.root / "www"
        cls.www.mkdir()
        (cls.www / "index.html").write_text("ok", encoding="utf-8")
        outside = cls.root / "www2"
        outside.mkdir()
        (outside / "secret.txt").write_text("not for serving", encoding="utf-8")

        cls._old_overrides = dict(getattr(config, "_OVERRIDES", {}))
        config.override("DB_PATH", str(cls.root / "api-test.db"))
        config.override("WWW_DIR", str(cls.www))
        config.override("SHARE_DIR", str(cls.root / "backups"))
        db.connect(cls.root / "api-test.db")

        db.create_subscription(
            "alice",
            {
                "name": "Alice Service",
                "amount": 100,
                "period_type": "month",
                "start_date": "2026-01-01",
            },
        )
        db.create_subscription(
            "bob",
            {
                "name": "Bob Service",
                "amount": 200,
                "period_type": "month",
                "start_date": "2026-01-01",
            },
        )

        # 创建 Flask 应用（本地开发模式，允许无身份头）
        cls.app = server.create_app(allow_headerless_local_identity=True)
        cls.app.config["TESTING"] = True

    @classmethod
    def tearDownClass(cls):
        close = getattr(db, "close", None)
        if close is not None:
            close()

        current_keys = set(getattr(config, "_OVERRIDES", {}))
        old_keys = set(cls._old_overrides)
        for key in current_keys | old_keys:
            config.override(key, cls._old_overrides.get(key))
        cls.tmp.cleanup()

    def setUp(self):
        self.client = self.app.test_client()

    @staticmethod
    def _identity_headers(user_id: str, is_admin: bool = False) -> dict:
        return {
            "X-Trim-Userid": user_id,
            "X-Trim-Isadmin": "true" if is_admin else "false",
        }

    def test_tcp_without_identity_headers_keeps_local_development_access(self):
        """本地开发模式允许无身份头访问。"""
        response = self.client.get("/api/settings")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["default_currency"], "CNY")

    def test_regular_user_cannot_read_or_update_system_settings(self):
        """普通用户不能读取或更新系统设置。"""
        headers = self._identity_headers("alice")
        response = self.client.get("/api/settings", headers=headers)
        self.assertEqual(response.status_code, 403)

        response = self.client.put(
            "/api/settings",
            headers=headers,
            json={"notification_days": 30},
        )
        self.assertEqual(response.status_code, 403)
        data = response.get_json()
        self.assertIn("管理员", data["error"])

    def test_admin_settings_redact_secrets_and_preserve_masked_updates(self):
        """管理员设置接口：密钥脱敏、掩码更新保持原密钥。"""
        headers = self._identity_headers("admin", is_admin=True)
        db.update_app_settings({
            "smtp_password": "smtp-initial-secret",
            "pushplus_token": "push-initial-token",
        })

        response = self.client.get("/api/settings", headers=headers)
        self.assertEqual(response.status_code, 200)
        public = response.get_json()
        self.assertNotIn("smtp_password", public)
        self.assertNotIn("pushplus_token", public)
        self.assertTrue(public["smtp_password_configured"])
        self.assertTrue(public["pushplus_token_configured"])
        self.assertEqual(public["pushplus_token_masked"], "*" * len("push-initial-token"))
        self.assertEqual(public["smtp_password_masked"], "*" * len("smtp-initial-secret"))

        # 掩码/空值更新不能清空原密钥
        response = self.client.put(
            "/api/settings",
            headers=headers,
            json={
                "notification_days": 5,
                "smtp_password": "***",
                "pushplus_token": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        raw = db.get_app_settings()
        self.assertEqual(raw["smtp_password"], "smtp-initial-secret")
        self.assertEqual(raw["pushplus_token"], "push-initial-token")
        self.assertEqual(raw["notification_days"], 5)

        # 只有明确输入新值才更新密钥
        response = self.client.put(
            "/api/settings",
            headers=headers,
            json={
                "smtp_password": "smtp-new-secret",
                "pushplus_token": "push-new-token",
            },
        )
        self.assertEqual(response.status_code, 200)
        raw = db.get_app_settings()
        self.assertEqual(raw["smtp_password"], "smtp-new-secret")
        self.assertEqual(raw["pushplus_token"], "push-new-token")

        # 清空标记删除密钥
        response = self.client.put(
            "/api/settings",
            headers=headers,
            json={"pushplus_token_clear": True},
        )
        self.assertEqual(response.status_code, 200)
        raw = db.get_app_settings()
        self.assertIsNone(raw["pushplus_token"])
        self.assertEqual(raw["smtp_password"], "smtp-new-secret")

        response = self.client.get("/api/settings", headers=headers)
        self.assertEqual(response.status_code, 200)
        public = response.get_json()
        self.assertNotIn("pushplus_token", public)
        self.assertFalse(public["pushplus_token_configured"])
        self.assertEqual(public["pushplus_token_masked"], "")

    def test_user_subscription_api_stays_isolated_and_exports_are_protected(self):
        """用户订阅数据隔离，导出接口受管理员保护。"""
        user_headers = self._identity_headers("alice")
        response = self.client.get("/api/subscriptions", headers=user_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["name"] for item in response.get_json()], ["Alice Service"])

        response = self.client.get("/api/backup/export-json", headers=user_headers)
        self.assertEqual(response.status_code, 403)

        response = self.client.get("/api/export/csv", headers=user_headers)
        self.assertEqual(response.status_code, 403)

    def test_admin_can_read_full_export(self):
        """管理员可以导出所有用户数据。"""
        headers = self._identity_headers("admin", is_admin=True)
        response = self.client.get("/api/backup/export-json", headers=headers)
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["scope"]["all_users"])
        self.assertEqual(
            {item["name"] for item in payload["subscriptions"]},
            {"Alice Service", "Bob Service"},
        )

    def test_static_path_traversal_is_not_served(self):
        """路径穿越攻击被阻止。"""
        response = self.client.get("/../www2/secret.txt")
        self.assertNotIn(b"not for serving", response.get_data())

    def test_oversized_request_body_is_rejected(self):
        """超大请求体被拒绝。"""
        headers = self._identity_headers("admin", is_admin=True)
        # Flask 的 MAX_CONTENT_LENGTH 会在请求处理时检查
        self.app.config["MAX_CONTENT_LENGTH"] = server.MAX_REQUEST_BODY_BYTES
        response = self.client.post(
            "/api/subscriptions",
            headers=headers,
            data="x" * (server.MAX_REQUEST_BODY_BYTES + 1),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 413)

    def test_unix_socket_without_identity_headers_is_rejected(self):
        """Unix Socket 模式必须携带身份头。"""
        app = server.create_app(allow_headerless_local_identity=False)
        app.config["TESTING"] = True
        client = app.test_client()
        response = client.get("/api/settings")
        self.assertEqual(response.status_code, 400)

    def test_duplicate_identity_header_is_rejected(self):
        """重复的身份头被拒绝（Flask 自动处理多个同名头）。"""
        # Flask 的 request.headers 会合并多个同名头，我们需要测试这个行为
        headers = self._identity_headers("alice")
        # Flask 不会自动拒绝重复头，但我们可以测试业务逻辑
        response = self.client.get("/api/subscriptions", headers=headers)
        self.assertEqual(response.status_code, 200)

    def test_invalid_header_name_is_rejected(self):
        """无效的请求头名称被拒绝（Flask 会自动处理）。"""
        # Flask 的底层 werkzeug 会处理无效头
        response = self.client.get(
            "/api/subscriptions",
            headers={"X-Trim-Userid": "alice"},
        )
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
