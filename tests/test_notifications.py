"""通知服务测试。

覆盖 parse_clock、is_do_not_disturb（含跨午夜）、
generate_notification_content。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from backend.services import notifications


# --------------------------------------------------------------------------- #
# parse_clock
# --------------------------------------------------------------------------- #


class TestParseClock:
    def test_valid_time(self):
        assert notifications.parse_clock("09:00") == 9 * 60

    def test_midnight(self):
        assert notifications.parse_clock("00:00") == 0

    def test_end_of_day(self):
        assert notifications.parse_clock("23:59") == 23 * 60 + 59

    def test_none_returns_none(self):
        assert notifications.parse_clock(None) is None

    def test_empty_returns_none(self):
        assert notifications.parse_clock("") is None

    def test_invalid_format_returns_none(self):
        assert notifications.parse_clock("9:00:00") is None

    def test_no_colon_returns_none(self):
        assert notifications.parse_clock("0900") is None

    def test_out_of_range_returns_none(self):
        assert notifications.parse_clock("25:00") is None
        assert notifications.parse_clock("12:60") is None

    def test_negative_returns_none(self):
        assert notifications.parse_clock("-1:00") is None


# --------------------------------------------------------------------------- #
# is_do_not_disturb
# --------------------------------------------------------------------------- #


class TestIsDoNotDisturb:
    def test_no_dnd_configured(self):
        """未配置免打扰时段时返回 False。"""
        settings = {"do_not_disturb_start": None, "do_not_disturb_end": None}
        assert notifications.is_do_not_disturb(settings) is False

    def test_same_start_end_returns_false(self):
        """起止时间相同时视为未启用。"""
        settings = {"do_not_disturb_start": "22:00", "do_not_disturb_end": "22:00"}
        assert notifications.is_do_not_disturb(settings) is False

    def test_inside_normal_range(self):
        """22:00 ~ 08:00 免打扰，23:30 在范围内。"""
        settings = {"do_not_disturb_start": "22:00", "do_not_disturb_end": "08:00"}
        now = datetime(2026, 3, 15, 23, 30)
        assert notifications.is_do_not_disturb(settings, now=now) is True

    def test_outside_normal_range(self):
        """22:00 ~ 08:00 免打扰，10:00 不在范围内。"""
        settings = {"do_not_disturb_start": "22:00", "do_not_disturb_end": "08:00"}
        now = datetime(2026, 3, 15, 10, 0)
        assert notifications.is_do_not_disturb(settings, now=now) is False

    def test_early_morning_inside(self):
        """跨午夜：凌晨 03:00 应在 22:00~08:00 内。"""
        settings = {"do_not_disturb_start": "22:00", "do_not_disturb_end": "08:00"}
        now = datetime(2026, 3, 16, 3, 0)
        assert notifications.is_do_not_disturb(settings, now=now) is True

    def test_just_at_start_boundary(self):
        """恰好在起始时刻应为免打扰。"""
        settings = {"do_not_disturb_start": "22:00", "do_not_disturb_end": "08:00"}
        now = datetime(2026, 3, 15, 22, 0)
        assert notifications.is_do_not_disturb(settings, now=now) is True

    def test_just_at_end_boundary(self):
        """恰好在结束时刻应为免打扰（跨午夜场景 end < start，08:00 是下界）。"""
        settings = {"do_not_disturb_start": "22:00", "do_not_disturb_end": "08:00"}
        now = datetime(2026, 3, 16, 8, 0)
        assert notifications.is_do_not_disturb(settings, now=now) is False

    def test_same_day_range(self):
        """同日内免打扰区间：12:00~14:00，13:00 在范围内。"""
        settings = {"do_not_disturb_start": "12:00", "do_not_disturb_end": "14:00"}
        now = datetime(2026, 3, 15, 13, 0)
        assert notifications.is_do_not_disturb(settings, now=now) is True

    def test_same_day_range_outside(self):
        """同日内免打扰区间：12:00~14:00，15:00 不在范围内。"""
        settings = {"do_not_disturb_start": "12:00", "do_not_disturb_end": "14:00"}
        now = datetime(2026, 3, 15, 15, 0)
        assert notifications.is_do_not_disturb(settings, now=now) is False


# --------------------------------------------------------------------------- #
# generate_notification_content
# --------------------------------------------------------------------------- #


class TestGenerateNotificationContent:
    def test_due_today(self):
        """到期日为今天时文案含 '今天到期'。"""
        today = date.today().isoformat()
        sub = {
            "name": "Netflix",
            "amount": 1990,
            "currency": "CNY",
            "next_due_date": today,
        }
        title, body = notifications.generate_notification_content(sub)
        assert "今天到期" in title
        assert "Netflix" in title
        assert "19.90" in body

    def test_due_in_future(self):
        """到期日为 3 天后时文案含 '3 天后到期'。"""
        future = (date.today() + timedelta(days=3)).isoformat()
        sub = {
            "name": "Spotify",
            "amount": 990,
            "currency": "USD",
            "next_due_date": future,
        }
        title, body = notifications.generate_notification_content(sub)
        assert "3 天后到期" in title
        assert "$" in body  # USD 符号

    def test_missing_due_date_raises(self):
        """缺少 next_due_date 应报错。"""
        with pytest.raises(ValueError, match="缺少下次到期日"):
            notifications.generate_notification_content({
                "name": "Test",
                "amount": 100,
                "currency": "CNY",
            })

    def test_invalid_due_date_raises(self):
        with pytest.raises(ValueError, match="格式无效"):
            notifications.generate_notification_content({
                "name": "Test",
                "amount": 100,
                "currency": "CNY",
                "next_due_date": "not-a-date",
            })
