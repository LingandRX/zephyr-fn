"""邮件通知模板与多部件邮件测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.utils.channels import email_templates
from backend.utils.channels.email import send_email


class TestEmailTemplates:
    def test_template_options_defined(self):
        opts = email_templates.TEMPLATE_OPTIONS
        assert len(opts) == 1
        assert opts[0]["id"] == "minimal"

    def test_render_minimal_test_mode(self):
        subject, text_body, html_body = email_templates.render_email_template(
            "minimal", is_test=True
        )
        assert "测试" in subject
        assert "Netflix" in text_body
        assert html_body is not None

    def test_render_minimal_real_sub(self):
        sub = {
            "name": "iCloud+ 2TB",
            "amount": 6800,
            "currency": "CNY",
            "period_type": "month",
            "next_due_date": "2026-10-01",
            "category_name": "云存储",
        }
        subject, text_body, html_body = email_templates.render_email_template("minimal", sub=sub)
        assert "iCloud+ 2TB" in subject
        assert "¥68.00" in text_body
        assert "iCloud+ 2TB" in text_body
        assert html_body is not None

    def test_any_template_id_falls_back_to_minimal(self):
        sub = {
            "name": "ChatGPT Plus",
            "amount": 2000,
            "currency": "USD",
            "period_type": "month",
            "next_due_date": "2026-10-05",
            "category_name": "AI 工具",
        }
        # 即使传入旧的 detailed 或未知 template_id，也统一渲染极简文本
        subject, text_body, html_body = email_templates.render_email_template("detailed", sub=sub)
        assert "ChatGPT Plus" in subject
        assert "$20.00" in text_body
        assert html_body is not None
        assert "【订阅到期提醒】" in text_body


class TestSendEmailMultipart:
    @patch("smtplib.SMTP_SSL")
    def test_send_email_with_html(self, mock_smtp_ssl):
        mock_server = MagicMock()
        mock_smtp_ssl.return_value = mock_server

        send_email(
            to_address="test@example.com",
            subject="测试主题",
            body="纯文本正文",
            body_html="<p>HTML 正文</p>",
            host="smtp.example.com",
            port=465,
            username="user@example.com",
            password="password",
        )

        mock_smtp_ssl.assert_called_once_with("smtp.example.com", 465, timeout=15)
        mock_server.login.assert_called_once_with("user@example.com", "password")
        mock_server.sendmail.assert_called_once()
        args = mock_server.sendmail.call_args[0]
        assert args[0] == "user@example.com"
        assert args[1] == ["test@example.com"]
        raw_msg = args[2]
        from email import message_from_string

        msg = message_from_string(raw_msg)
        assert msg.is_multipart()
        parts = [p.get_payload(decode=True).decode("utf-8") for p in msg.get_payload()]
        assert "纯文本正文" in parts[0]
        assert "<p>HTML 正文</p>" in parts[1]
