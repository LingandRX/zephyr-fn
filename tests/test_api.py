"""HTTP API 安全边界回归测试。

使用 Flask 测试客户端与统一响应信封 {code, message, data}。
"""
from __future__ import annotations

import json
import unittest

from helpers import AppTestCase
from backend import config
from backend.extensions import db
from backend.services import subscriptions as sub_service
from backend.storage import repositories


class FlaskApiSecurityTests(AppTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # 静态目录：index.html + 越界目录（路径穿越测试用）
        cls.www = cls.root / "www"
        cls.www.mkdir()
        (cls.www / "index.html").write_text("ok", encoding="utf-8")
        outside = cls.root / "www2"
        outside.mkdir()
        (outside / "secret.txt").write_text("not for serving", encoding="utf-8")
        config.override("WWW_DIR", str(cls.www))

        with cls.ctx():
            sub_service.create_subscription(
                "alice",
                {
                    "name": "Alice Service",
                    "amount": 100,
                    "period_type": "month",
                    "start_date": "2026-01-01",
                },
            )
            sub_service.create_subscription(
                "bob",
                {
                    "name": "Bob Service",
                    "amount": 200,
                    "period_type": "month",
                    "start_date": "2026-01-01",
                },
            )

    def setUp(self):
        super().setUp()
        self.client = self.app.test_client()

    @staticmethod
    def _identity_headers(user_id: str, is_admin: bool = False) -> dict:
        return {
            "X-Trim-Userid": user_id,
            "X-Trim-Isadmin": "true" if is_admin else "false",
        }

    @staticmethod
    def _unwrap(payload: dict) -> dict:
        """解包统一信封：校验 code == 0 并返回 data。"""
        assert payload["code"] == 0, payload
        return payload["data"]

    def test_tcp_without_identity_headers_keeps_local_development_access(self):
        """本地开发模式允许无身份头访问。"""
        response = self.client.get("/api/settings")
        self.assertEqual(response.status_code, 200)
        data = self._unwrap(response.get_json())
        self.assertEqual(data["default_currency"], "CNY")

    def test_regular_user_cannot_read_or_update_system_settings(self):
        """普通用户不能读取或更新系统设置。"""
        headers = self._identity_headers("alice")
        response = self.client.get("/api/settings", headers=headers)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["code"], 403)

        response = self.client.put(
            "/api/settings",
            headers=headers,
            json={"notification_days": 30},
        )
        self.assertEqual(response.status_code, 403)
        data = response.get_json()
        self.assertIn("管理员", data["message"])

    def test_admin_settings_redact_secrets_and_preserve_masked_updates(self):
        """管理员设置接口：密钥脱敏、掩码更新保持原密钥。"""
        headers = self._identity_headers("admin", is_admin=True)
        with self.ctx():
            repositories.update_app_settings({
                "smtp_password": "smtp-initial-secret",
                "pushplus_token": "push-initial-token",
            })

        response = self.client.get("/api/settings", headers=headers)
        self.assertEqual(response.status_code, 200)
        public = self._unwrap(response.get_json())
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
        raw = repositories.get_app_settings()
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
        raw = repositories.get_app_settings()
        self.assertEqual(raw["smtp_password"], "smtp-new-secret")
        self.assertEqual(raw["pushplus_token"], "push-new-token")

        # 清空标记删除密钥
        response = self.client.put(
            "/api/settings",
            headers=headers,
            json={"pushplus_token_clear": True},
        )
        self.assertEqual(response.status_code, 200)
        raw = repositories.get_app_settings()
        self.assertIsNone(raw["pushplus_token"])
        self.assertEqual(raw["smtp_password"], "smtp-new-secret")

        response = self.client.get("/api/settings", headers=headers)
        self.assertEqual(response.status_code, 200)
        public = self._unwrap(response.get_json())
        self.assertNotIn("pushplus_token", public)
        self.assertFalse(public["pushplus_token_configured"])
        self.assertEqual(public["pushplus_token_masked"], "")

    def test_user_subscription_api_stays_isolated_and_exports_are_protected(self):
        """用户订阅数据隔离，导出接口受管理员保护。"""
        user_headers = self._identity_headers("alice")
        response = self.client.get("/api/subscriptions", headers=user_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["name"] for item in self._unwrap(response.get_json())],
            ["Alice Service"],
        )

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
        response = self.client.post(
            "/api/subscriptions",
            headers=headers,
            data="x" * (config.MAX_REQUEST_BODY_BYTES + 1),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.get_json()["code"], 413)

    def test_unix_socket_without_identity_headers_is_rejected(self):
        """Unix Socket 模式必须携带身份头。"""
        app = create_app_production_like()
        app.config["TESTING"] = True

        def _cleanup():
            with app.app_context():
                db.session.remove()
                db.engine.dispose()

        self.addCleanup(_cleanup)
        client = app.test_client()
        response = client.get("/api/settings")
        self.assertEqual(response.status_code, 401)

    def test_subscription_crud_returns_unified_envelope(self):
        """订阅 CRUD 返回统一信封 {code, message, data}。"""
        # 使用独立用户，避免污染其他测试的 alice/bob 数据
        headers = self._identity_headers("crud-user")
        # 创建
        response = self.client.post(
            "/api/subscriptions",
            headers=headers,
            json={"name": "Spotify", "amount": 1500, "period_type": "month",
                  "start_date": "2026-01-01"},
        )
        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(body["code"], 0)
        self.assertEqual(body["message"], "ok")
        self.assertEqual(body["data"]["name"], "Spotify")
        sub_id = body["data"]["id"]

        # 查询单个
        response = self.client.get(f"/api/subscriptions/{sub_id}", headers=headers)
        self.assertEqual(response.get_json()["data"]["name"], "Spotify")

        # 更新
        response = self.client.put(
            f"/api/subscriptions/{sub_id}", headers=headers,
            json={"amount": 1800},
        )
        self.assertEqual(response.get_json()["data"]["amount"], 1800)

        # 续费
        response = self.client.post(f"/api/subscriptions/{sub_id}/renew", headers=headers)
        self.assertEqual(response.status_code, 200)

        # 删除
        response = self.client.delete(f"/api/subscriptions/{sub_id}", headers=headers)
        self.assertEqual(response.get_json()["data"]["ok"], True)

        # 不存在 -> 404 信封
        response = self.client.get(f"/api/subscriptions/{sub_id}", headers=headers)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["code"], 404)


def create_app_production_like():
    """创建不允许无身份头访问的应用（模拟 Unix Socket 网关模式）。"""
    from backend.app import create_app as _factory
    return _factory(allow_headerless_local_identity=False)


if __name__ == "__main__":
    unittest.main()
