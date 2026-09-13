"""Schema 校验测试。

覆盖 SubscriptionSchema (create / update)、SettingsSchema (密钥掩码)
和 CategorySchema (名称归一化)。
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.schemas.subscription import SubscriptionSchema
from backend.schemas.settings import SettingsSchema
from backend.schemas.category import normalize_category_name, normalize_icon
from backend.domain.exceptions import ValidationError


# --------------------------------------------------------------------------- #
# SubscriptionSchema.validate_create
# --------------------------------------------------------------------------- #


class TestSubscriptionSchemaCreate:
    def _valid_payload(self, **overrides):
        base = {
            "name": "Netflix",
            "amount": 1990,
            "currency": "CNY",
            "period_type": "month",
            "auto_renew": True,
            "start_date": "2026-01-15",
        }
        base.update(overrides)
        return base

    def test_valid_create(self):
        result = SubscriptionSchema.validate_create(self._valid_payload())
        assert result["name"] == "Netflix"
        assert result["amount"] == 1990
        assert result["currency"] == "CNY"
        assert result["period_type"] == "month"
        assert result["renewal_policy"] == "auto"

    def test_defaults_applied(self):
        """省略可选字段时使用默认值。"""
        result = SubscriptionSchema.validate_create({"name": "Test"})
        assert result["amount"] == 0
        assert result["currency"] == "CNY"
        assert result["period_type"] == "month"
        assert result["auto_renew"] is True
        assert result["lifecycle"] == "active"

    def test_empty_name_raises(self):
        with pytest.raises(ValidationError, match="不能为空"):
            SubscriptionSchema.validate_create(self._valid_payload(name=""))

    def test_null_name_raises(self):
        with pytest.raises(ValidationError, match="不能为空"):
            SubscriptionSchema.validate_create(self._valid_payload(name=None))

    def test_invalid_currency_raises(self):
        with pytest.raises(ValidationError):
            SubscriptionSchema.validate_create(self._valid_payload(currency="EUR"))

    def test_negative_amount_raises(self):
        with pytest.raises(ValidationError, match="不能为负数"):
            SubscriptionSchema.validate_create(self._valid_payload(amount=-100))

    def test_custom_period(self):
        result = SubscriptionSchema.validate_create(self._valid_payload(
            period_type="custom",
            custom_period_value=14,
            custom_period_unit="day",
        ))
        assert result["period_type"] == "custom"
        assert result["custom_period_value"] == 14

    def test_category_and_notes_cleaned(self):
        result = SubscriptionSchema.validate_create(self._valid_payload(
            category_id="  cat-123  ",
            notes="  some note  ",
        ))
        assert result["category_id"] == "cat-123"
        assert result["notes"] == "some note"

    def test_none_input_raises(self):
        with pytest.raises(ValidationError, match="必须是对象"):
            SubscriptionSchema.validate_create(None)


# --------------------------------------------------------------------------- #
# SubscriptionSchema.validate_update
# --------------------------------------------------------------------------- #


class TestSubscriptionSchemaUpdate:
    def test_partial_name_update(self):
        result = SubscriptionSchema.validate_update({"name": "Updated Name"})
        assert result["name"] == "Updated Name"
        assert "amount" not in result  # 未请求的字段不应出现

    def test_partial_amount_update(self):
        result = SubscriptionSchema.validate_update({"amount": 2990})
        assert result["amount"] == 2990

    def test_empty_name_raises(self):
        with pytest.raises(ValidationError, match="不能为空"):
            SubscriptionSchema.validate_update({"name": ""})

    def test_null_name_raises(self):
        with pytest.raises(ValidationError, match="不能为空"):
            SubscriptionSchema.validate_update({"name": None})

    def test_empty_request_returns_empty_dict(self):
        result = SubscriptionSchema.validate_update({})
        assert result == {}

    def test_invalid_period_type_raises(self):
        with pytest.raises(ValidationError):
            SubscriptionSchema.validate_update({"period_type": "weekly"})


# --------------------------------------------------------------------------- #
# SettingsSchema.load
# --------------------------------------------------------------------------- #


class TestSettingsSchema:
    def test_normal_field_update(self):
        result = SettingsSchema.load({"notification_days": 14})
        assert result["notification_days"] == 14

    def test_secret_placeholder_not_overwritten(self):
        """*** 掩码占位符不应覆盖原密钥。"""
        result = SettingsSchema.load({"smtp_password": "***"})
        assert "smtp_password" not in result

    def test_redacted_placeholder(self):
        result = SettingsSchema.load({"smtp_password": "[redacted]"})
        assert "smtp_password" not in result

    def test_chinese_placeholder(self):
        result = SettingsSchema.load({"smtp_password": "已配置"})
        assert "smtp_password" not in result

    def test_actual_secret_is_updated(self):
        result = SettingsSchema.load({"smtp_password": "new-password-123"})
        assert result["smtp_password"] == "new-password-123"

    def test_clear_secret_with_field(self):
        """{field}_clear 标记显式清空密钥。"""
        result = SettingsSchema.load({"smtp_password": "***", "smtp_password_clear": True})
        assert result["smtp_password"] is None

    def test_bool_field_conversion(self):
        result = SettingsSchema.load({"email_enabled": True, "pushplus_enabled": 0})
        assert result["email_enabled"] == 1
        assert result["pushplus_enabled"] == 0

    def test_float_field_conversion(self):
        result = SettingsSchema.load({"exchange_rate_usd": "7.5"})
        assert result["exchange_rate_usd"] == 7.5

    def test_configured_fields_filtered_out(self):
        """*_configured 输出字段不允许回写。"""
        result = SettingsSchema.load({
            "smtp_password_configured": True,
            "notification_days": 7,
        })
        assert "smtp_password_configured" not in result

    def test_non_mapping_raises(self):
        with pytest.raises(ValidationError, match="必须是对象"):
            SettingsSchema.load("not-a-dict")


# --------------------------------------------------------------------------- #
# CategorySchema
# --------------------------------------------------------------------------- #


class TestCategorySchema:
    def test_basic_name(self):
        assert normalize_category_name("影音") == "影音"

    def test_fullwidth_to_halfwidth(self):
        """全角字符应自动转半角。"""
        assert normalize_category_name("ＡＩ工具") == "AI工具"

    def test_whitespace_trimmed(self):
        assert normalize_category_name("  工具  ") == "工具"

    def test_nfc_normalization(self):
        """NFC 组合字符归一化。"""
        # NFC 归一化在大多数系统上是幂等的
        result = normalize_category_name("测 试")
        assert result == "测 试"

    def test_empty_name_raises(self):
        with pytest.raises(ValidationError, match="不能为空"):
            normalize_category_name("")

    def test_only_whitespace_raises(self):
        with pytest.raises(ValidationError, match="不能为空"):
            normalize_category_name("   ")

    def test_illegal_chars_raises(self):
        for ch in '<>"\'&':
            with pytest.raises(ValidationError, match="不能包含"):
                normalize_category_name(f"test{ch}")

    def test_icon_valid_emoji(self):
        assert normalize_icon("🎬") == "🎬"

    def test_icon_none(self):
        assert normalize_icon(None) is None

    def test_icon_empty(self):
        assert normalize_icon("") is None

    def test_icon_too_long_raises(self):
        with pytest.raises(ValidationError, match="emoji"):
            normalize_icon("🎬🎬🎬")

    def test_icon_alpha_raises(self):
        with pytest.raises(ValidationError, match="emoji"):
            normalize_icon("abc")
