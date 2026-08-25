"""HTTP API 安全边界回归测试。

测试只使用 Python 标准库，并为每次测试类创建临时数据库、静态目录和备份
目录。请求通过 Handler 级 fake rfile/wfile/server harness 注入，不监听端口，
也不访问外网或依赖第三方库。
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "backend"))

import config
import db
import server


class ApiSecurityTests(unittest.TestCase):
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

    @staticmethod
    def _identity_headers(user_id: str, is_admin: bool = False) -> list[str]:
        return [
            f"X-Trim-Userid: {user_id}",
            f"X-Trim-Isadmin: {'true' if is_admin else 'false'}",
        ]

    @classmethod
    def _request_bytes(
        cls,
        path: str,
        *,
        method: str = "GET",
        headers: list[str] | None = None,
        body: bytes = b"",
        raw_header_lines: list[str] | None = None,
    ) -> bytes:
        lines = [f"{method} {path} HTTP/1.1", "Host: api-test"]
        lines.extend(headers or [])
        lines.extend(raw_header_lines or [])
        if body and not any(line.lower().startswith("content-length:") for line in lines):
            lines.append(f"Content-Length: {len(body)}")
        return ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + body

    @staticmethod
    def _parse_response(raw: bytes) -> tuple[int, dict[str, str], bytes]:
        head, separator, body = raw.partition(b"\r\n\r\n")
        if not separator:
            raise AssertionError(f"响应缺少 Header 结束符: {raw!r}")
        lines = head.decode("latin-1").split("\r\n")
        status_parts = lines[0].split(" ", 2)
        status = int(status_parts[1])
        response_headers = {}
        for line in lines[1:]:
            name, separator, value = line.partition(":")
            if separator:
                response_headers[name.lower()] = value.strip()
        return status, response_headers, body

    @classmethod
    def _request(cls, request: bytes, *, allow_headerless_local_identity: bool):
        """直接驱动 Handler，模拟 socketserver 已建立的请求上下文。"""
        handler = server.Handler.__new__(server.Handler)
        handler.server = SimpleNamespace(
            allow_headerless_local_identity=allow_headerless_local_identity
        )
        handler.rfile = io.BytesIO(request)
        handler.wfile = io.BytesIO()
        handler._handle_request()
        return cls._parse_response(handler.wfile.getvalue())

    @classmethod
    def _tcp_request(cls, request: bytes):
        return cls._request(
            request,
            allow_headerless_local_identity=server.ThreadingTCPServer.allow_headerless_local_identity,
        )

    @classmethod
    def _unix_request(cls, request: bytes):
        return cls._request(
            request,
            allow_headerless_local_identity=server.ThreadingUnixServer.allow_headerless_local_identity,
        )

    def test_tcp_without_identity_headers_keeps_local_development_access(self):
        self.assertTrue(server.ThreadingTCPServer.allow_headerless_local_identity)
        status, _headers, body = self._tcp_request(
            self._request_bytes("/api/settings")
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["default_currency"], "CNY")

    def test_regular_user_cannot_read_or_update_system_settings(self):
        headers = self._identity_headers("alice")
        status, _response_headers, _body = self._tcp_request(
            self._request_bytes("/api/settings", headers=headers)
        )
        self.assertEqual(status, 403)

        status, _response_headers, body = self._tcp_request(
            self._request_bytes(
                "/api/settings",
                method="PUT",
                headers=headers,
                body=b'{"notification_days": 30}',
            )
        )
        self.assertEqual(status, 403)
        self.assertIn("管理员", body.decode("utf-8"))

    def test_admin_settings_redact_secrets_and_preserve_masked_updates(self):
        headers = self._identity_headers("admin", is_admin=True)
        db.update_app_settings({
            "smtp_password": "smtp-initial-secret",
            "pushplus_token": "push-initial-token",
        })

        status, _response_headers, body = self._tcp_request(
            self._request_bytes("/api/settings", headers=headers)
        )
        self.assertEqual(status, 200)
        public = json.loads(body)
        self.assertNotIn("smtp_password", public)
        self.assertNotIn("pushplus_token", public)
        self.assertTrue(public["smtp_password_configured"])
        self.assertTrue(public["pushplus_token_configured"])
        # 只暴露与真实长度一致的星号掩码，不泄露原文
        self.assertEqual(public["pushplus_token_masked"], "*" * len("push-initial-token"))
        self.assertEqual(public["smtp_password_masked"], "*" * len("smtp-initial-secret"))

        # 页面自动保存时可能携带空值或掩码；这类更新不能清空原密钥。
        status, _response_headers, _body = self._tcp_request(
            self._request_bytes(
                "/api/settings",
                method="PUT",
                headers=headers,
                body=json.dumps({
                    "notification_days": 5,
                    "smtp_password": "***",
                    "pushplus_token": "",
                }).encode("utf-8"),
            )
        )
        self.assertEqual(status, 200)
        raw = db.get_app_settings()
        self.assertEqual(raw["smtp_password"], "smtp-initial-secret")
        self.assertEqual(raw["pushplus_token"], "push-initial-token")
        self.assertEqual(raw["notification_days"], 5)

        # 只有明确输入新值才更新密钥。
        status, _response_headers, _body = self._tcp_request(
            self._request_bytes(
                "/api/settings",
                method="PUT",
                headers=headers,
                body=json.dumps({
                    "smtp_password": "smtp-new-secret",
                    "pushplus_token": "push-new-token",
                }).encode("utf-8"),
            )
        )
        self.assertEqual(status, 200)
        raw = db.get_app_settings()
        self.assertEqual(raw["smtp_password"], "smtp-new-secret")
        self.assertEqual(raw["pushplus_token"], "push-new-token")

        # 前端「清空输入框即移除」：显式 *_clear 标记才能删除已保存密钥，
        # 空值/掩码仍然只是“保持原密钥”。
        status, _response_headers, _body = self._tcp_request(
            self._request_bytes(
                "/api/settings",
                method="PUT",
                headers=headers,
                body=json.dumps({
                    "pushplus_token_clear": True,
                }).encode("utf-8"),
            )
        )
        self.assertEqual(status, 200)
        raw = db.get_app_settings()
        self.assertIsNone(raw["pushplus_token"])
        self.assertEqual(raw["smtp_password"], "smtp-new-secret")

        status, _response_headers, body = self._tcp_request(
            self._request_bytes("/api/settings", headers=headers)
        )
        self.assertEqual(status, 200)
        public = json.loads(body)
        self.assertNotIn("pushplus_token", public)
        self.assertFalse(public["pushplus_token_configured"])
        self.assertEqual(public["pushplus_token_masked"], "")

    def test_user_subscription_api_stays_isolated_and_exports_are_protected(self):
        user_headers = self._identity_headers("alice")
        status, _response_headers, body = self._tcp_request(
            self._request_bytes("/api/subscriptions", headers=user_headers)
        )
        self.assertEqual(status, 200)
        self.assertEqual([item["name"] for item in json.loads(body)], ["Alice Service"])

        status, _response_headers, _body = self._tcp_request(
            self._request_bytes("/api/backup/export-json", headers=user_headers)
        )
        self.assertEqual(status, 403)
        status, _response_headers, _body = self._tcp_request(
            self._request_bytes("/api/export/csv", headers=user_headers)
        )
        self.assertEqual(status, 403)

    def test_admin_can_read_full_export(self):
        headers = self._identity_headers("admin", is_admin=True)
        status, _response_headers, body = self._tcp_request(
            self._request_bytes("/api/backup/export-json", headers=headers)
        )
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertTrue(payload["scope"]["all_users"])
        self.assertEqual(
            {item["name"] for item in payload["subscriptions"]},
            {"Alice Service", "Bob Service"},
        )

    def test_static_path_traversal_is_not_served(self):
        status, _response_headers, body = self._tcp_request(
            self._request_bytes("/../www2/secret.txt")
        )
        self.assertEqual(status, 404)
        self.assertNotIn(b"not for serving", body)

    def test_oversized_request_body_is_rejected_before_reading_body(self):
        request = self._request_bytes(
            "/api/subscriptions",
            method="POST",
            headers=[f"Content-Length: {server.MAX_REQUEST_BODY_BYTES + 1}"],
        )
        status, _response_headers, body = self._tcp_request(request)
        self.assertEqual(status, 413)
        self.assertIn("请求体过大", body.decode("utf-8"))

    def test_invalid_header_name_is_rejected(self):
        request = self._request_bytes(
            "/api/subscriptions",
            raw_header_lines=["Bad Header: value"],
        )
        status, _response_headers, body = self._tcp_request(request)
        self.assertEqual(status, 400)
        self.assertIn("请求头名称格式错误", body.decode("utf-8"))

    def test_duplicate_identity_header_is_rejected(self):
        request = self._request_bytes(
            "/api/subscriptions",
            raw_header_lines=[
                "X-Trim-Userid: alice",
                "X-Trim-Userid: bob",
            ],
        )
        status, _response_headers, body = self._tcp_request(request)
        self.assertEqual(status, 400)
        self.assertIn("请求头重复", body.decode("utf-8"))

    def test_test_email_endpoint(self):
        # 普通用户无权调用
        req = self._request_bytes(
            "/api/notifications/test-email",
            method="POST",
            headers=self._identity_headers("alice", is_admin=False),
            body=b"{}",
        )
        status, _, body = self._tcp_request(req)
        self.assertEqual(status, 403)

        # 管理员未配置 host 时报错
        req = self._request_bytes(
            "/api/notifications/test-email",
            method="POST",
            headers=self._identity_headers("admin", is_admin=True),
            body=b"{}",
        )
        status, _, body = self._tcp_request(req)
        self.assertEqual(status, 400)
        self.assertIn("SMTP", body.decode("utf-8"))

    def test_test_pushplus_endpoint(self):
        # 普通用户无权调用
        req = self._request_bytes(
            "/api/notifications/test-pushplus",
            method="POST",
            headers=self._identity_headers("alice", is_admin=False),
            body=b"{}",
        )
        status, _, body = self._tcp_request(req)
        self.assertEqual(status, 403)

        # 临时清空已配置的 token 进行测试
        old_settings = db.get_app_settings()
        with db._lock:
            db._require_conn().execute("UPDATE app_settings SET pushplus_token=NULL WHERE id=1")
            db._conn.commit()

        try:
            # 管理员未配置 token 且未传入 token 时报错
            req = self._request_bytes(
                "/api/notifications/test-pushplus",
                method="POST",
                headers=self._identity_headers("admin", is_admin=True),
                body=b"{}",
            )
            status, _, body = self._tcp_request(req)
            self.assertEqual(status, 400)
            self.assertIn("PushPlus Token", body.decode("utf-8"))
        finally:
            with db._lock:
                db._require_conn().execute(
                    "UPDATE app_settings SET pushplus_token=? WHERE id=1",
                    (old_settings.get("pushplus_token"),),
                )
                db._conn.commit()

    def test_unix_socket_without_identity_headers_is_rejected(self):
        self.assertFalse(server.ThreadingUnixServer.allow_headerless_local_identity)
        status, _response_headers, body = self._unix_request(
            self._request_bytes("/api/settings")
        )
        self.assertEqual(status, 400)
        self.assertIn("X-Trim-Userid", body.decode("utf-8"))

        status, _response_headers, _body = self._unix_request(
            self._request_bytes(
                "/api/settings",
                headers=self._identity_headers("admin", is_admin=True),
            )
        )
        self.assertEqual(status, 200)


if __name__ == "__main__":
    unittest.main()
