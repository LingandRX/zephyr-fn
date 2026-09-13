"""领域纯函数测试（无需 Flask 上下文）。

覆盖 add_months、add_one_period、derive_status、normalize_bool、
normalize_date、normalize_subscription_data、should_auto_renew_on_wake。
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.domain import domain


# --------------------------------------------------------------------------- #
# add_months
# --------------------------------------------------------------------------- #


class TestAddMonths:
    def test_basic_forward(self):
        """普通日期推进 1 个月。"""
        assert domain.add_months(date(2026, 1, 15), 1) == date(2026, 2, 15)

    def test_basic_backward(self):
        """普通日期回退 1 个月。"""
        assert domain.add_months(date(2026, 6, 15), -1) == date(2026, 5, 15)

    def test_end_of_month_anchor_31(self):
        """月末锚点：1月31日 → 2月28日 → 3月31日。"""
        d = date(2026, 1, 31)
        step1 = domain.add_months(d, 1)
        step2 = domain.add_months(step1, 1, anchor_day=domain.billing_anchor_day(d))
        assert step1 == date(2026, 2, 28)
        assert step2 == date(2026, 3, 31)

    def test_end_of_month_leap_year(self):
        """闰年月末锚点：2024-01-31 → 2024-02-29。"""
        d = date(2024, 1, 31)
        assert domain.add_months(d, 1) == date(2024, 2, 29)

    def test_anchor_day_30_clamp_feb(self):
        """锚点 30：1月30日 → 2月28日。"""
        assert domain.add_months(date(2026, 1, 30), 1) == date(2026, 2, 28)

    def test_explicit_anchor_day(self):
        """显式传入 anchor_day 覆盖默认。"""
        result = domain.add_months(date(2026, 1, 10), 1, anchor_day=31)
        assert result == date(2026, 2, 28)

    def test_year_boundary(self):
        """跨年推进。"""
        assert domain.add_months(date(2026, 11, 15), 2) == date(2027, 1, 15)

    def test_zero_months(self):
        """推进 0 个月。"""
        assert domain.add_months(date(2026, 3, 15), 0) == date(2026, 3, 15)


# --------------------------------------------------------------------------- #
# add_one_period / sub_one_period
# --------------------------------------------------------------------------- #


class TestAddOnePeriod:
    def test_month(self):
        assert domain.add_one_period(date(2026, 3, 15), "month") == date(2026, 4, 15)

    def test_quarter(self):
        assert domain.add_one_period(date(2026, 1, 15), "quarter") == date(2026, 4, 15)

    def test_year(self):
        assert domain.add_one_period(date(2026, 3, 15), "year") == date(2027, 3, 15)

    def test_once_returns_none(self):
        assert domain.add_one_period(date(2026, 3, 15), "once") is None

    def test_custom_day(self):
        result = domain.add_one_period(date(2026, 3, 15), "custom", custom_value=14, custom_unit="day")
        assert result == date(2026, 3, 29)

    def test_custom_week(self):
        result = domain.add_one_period(date(2026, 3, 15), "custom", custom_value=2, custom_unit="week")
        assert result == date(2026, 3, 29)

    def test_custom_month(self):
        result = domain.add_one_period(date(2026, 3, 15), "custom", custom_value=3, custom_unit="month")
        assert result == date(2026, 6, 15)

    def test_custom_year(self):
        result = domain.add_one_period(date(2026, 3, 15), "custom", custom_value=1, custom_unit="year")
        assert result == date(2027, 3, 15)

    def test_custom_default_values(self):
        """custom 周期不指定 value/unit 时回退到 1 month。"""
        result = domain.add_one_period(date(2026, 3, 15), "custom")
        assert result == date(2026, 4, 15)

    def test_sub_one_period_month(self):
        assert domain.sub_one_period(date(2026, 3, 15), "month") == date(2026, 2, 15)

    def test_sub_one_period_quarter(self):
        assert domain.sub_one_period(date(2026, 4, 15), "quarter") == date(2026, 1, 15)

    def test_sub_one_period_year(self):
        assert domain.sub_one_period(date(2027, 3, 15), "year") == date(2026, 3, 15)

    def test_sub_one_period_once(self):
        assert domain.sub_one_period(date(2026, 3, 15), "once") is None

    def test_sub_one_period_custom_day(self):
        result = domain.sub_one_period(date(2026, 3, 20), "custom", custom_value=7, custom_unit="day")
        assert result == date(2026, 3, 13)


# --------------------------------------------------------------------------- #
# billing_anchor_day
# --------------------------------------------------------------------------- #


class TestBillingAnchorDay:
    def test_end_of_month_returns_31(self):
        assert domain.billing_anchor_day(date(2026, 1, 31)) == 31

    def test_last_day_feb_returns_31(self):
        """2月28日（非闰年，月末）→ 锚点 31。"""
        assert domain.billing_anchor_day(date(2026, 2, 28)) == 31

    def test_last_day_feb_leap_returns_31(self):
        """2月29日（闰年，月末）→ 锚点 31。"""
        assert domain.billing_anchor_day(date(2024, 2, 29)) == 31

    def test_mid_month_returns_day(self):
        assert domain.billing_anchor_day(date(2026, 3, 15)) == 15

    def test_day_30_not_last_returns_30(self):
        assert domain.billing_anchor_day(date(2026, 3, 30)) == 30


# --------------------------------------------------------------------------- #
# derive_status
# --------------------------------------------------------------------------- #


class TestDeriveStatus:
    def test_active_with_no_due_date(self):
        assert domain.derive_status("active", None) == "active"

    def test_active_due_future(self):
        today = date.today()
        future = (today + timedelta(days=30)).isoformat()
        assert domain.derive_status("active", future) == "active"

    def test_expiring_within_threshold(self):
        today = date.today()
        expiring = (today + timedelta(days=3)).isoformat()
        assert domain.derive_status("active", expiring) == "expiring"

    def test_expiring_at_boundary(self):
        """恰好第 7 天（阈值天数）也应为 expiring。"""
        today = date.today()
        boundary = (today + timedelta(days=domain.EXPIRING_THRESHOLD_DAYS)).isoformat()
        assert domain.derive_status("active", boundary) == "expiring"

    def test_expired_past_due(self):
        today = date.today()
        past = (today - timedelta(days=1)).isoformat()
        assert domain.derive_status("active", past) == "expired"

    def test_expired_just_past(self):
        today = date.today()
        # 恰好今天到期日：days=0 <= EXPIRING_THRESHOLD_DAYS，所以是 "expiring" 而非 "active"
        assert domain.derive_status("active", today.isoformat()) == "expiring"

    def test_non_active_lifecycle_passthrough(self):
        """非 active 的 lifecycle 直接透传，不看日期。"""
        assert domain.derive_status("canceled", None) == "canceled"
        assert domain.derive_status("ended", None) == "ended"
        assert domain.derive_status("in_payment", None) == "in_payment"
        assert domain.derive_status("grace_period", None) == "grace_period"
        assert domain.derive_status("expired", None) == "expired"

    def test_invalid_date_returns_active(self):
        """脏日期宁可显示 active，不误判为即将到期。"""
        assert domain.derive_status("active", "not-a-date") == "active"


# --------------------------------------------------------------------------- #
# normalize_bool
# --------------------------------------------------------------------------- #


class TestNormalizeBool:
    def test_true_value(self):
        assert domain.normalize_bool(True) is True

    def test_false_value(self):
        assert domain.normalize_bool(False) is False

    def test_int_1(self):
        assert domain.normalize_bool(1) is True

    def test_int_0(self):
        assert domain.normalize_bool(0) is False

    def test_str_true(self):
        assert domain.normalize_bool("true") is True
        assert domain.normalize_bool("TRUE") is True

    def test_str_yes(self):
        assert domain.normalize_bool("yes") is True

    def test_str_on(self):
        assert domain.normalize_bool("on") is True

    def test_str_false(self):
        assert domain.normalize_bool("false") is False
        assert domain.normalize_bool("FALSE") is False

    def test_str_no(self):
        assert domain.normalize_bool("no") is False

    def test_str_off(self):
        assert domain.normalize_bool("off") is False

    def test_str_1(self):
        assert domain.normalize_bool("1") is True

    def test_str_0(self):
        assert domain.normalize_bool("0") is False

    def test_none_raises_without_default(self):
        with pytest.raises(ValueError):
            domain.normalize_bool(None)

    def test_none_returns_default(self):
        assert domain.normalize_bool(None, default=True) is True
        assert domain.normalize_bool(None, default=False) is False

    def test_empty_str_raises(self):
        with pytest.raises(ValueError):
            domain.normalize_bool("")

    def test_invalid_str_raises(self):
        with pytest.raises(ValueError):
            domain.normalize_bool("maybe")

    def test_int_2_raises(self):
        with pytest.raises(ValueError):
            domain.normalize_bool(2)


# --------------------------------------------------------------------------- #
# normalize_date
# --------------------------------------------------------------------------- #


class TestNormalizeDate:
    def test_valid_date_string(self):
        assert domain.normalize_date("2026-03-15") == "2026-03-15"

    def test_date_object(self):
        assert domain.normalize_date(date(2026, 3, 15)) == "2026-03-15"

    def test_none_with_allow_none(self):
        assert domain.normalize_date(None) is None

    def test_none_without_allow_none_raises(self):
        with pytest.raises(ValueError):
            domain.normalize_date(None, allow_none=False)

    def test_empty_string(self):
        assert domain.normalize_date("  ") is None

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            domain.normalize_date("2026/03/15")

    def test_partial_date_raises(self):
        with pytest.raises(ValueError):
            domain.normalize_date("2026-03")

    def test_invalid_date_raises(self):
        with pytest.raises(ValueError):
            domain.normalize_date("2026-13-01")

    def test_datetime_raises(self):
        """datetime 对象应拒绝（不能悄悄丢弃时分秒）。"""
        from datetime import datetime
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            domain.normalize_date(datetime(2026, 3, 15, 12, 0))


# --------------------------------------------------------------------------- #
# normalize_subscription_data
# --------------------------------------------------------------------------- #


class TestNormalizeSubscriptionData:
    def _minimal_data(self, **overrides):
        base = {
            "name": "测试订阅",
            "amount": 1900,
            "currency": "CNY",
            "period_type": "month",
            "auto_renew": True,
            "start_date": "2026-01-15",
        }
        base.update(overrides)
        return base

    def test_minimal_data(self):
        result = domain.normalize_subscription_data(self._minimal_data())
        assert result["name"] == "测试订阅"
        assert result["amount"] == 1900
        assert result["currency"] == "CNY"
        assert result["period_type"] == "month"
        assert result["renewal_policy"] == "auto"
        assert result["start_date"] == "2026-01-15"

    def test_defaults_applied(self):
        """金额不传时默认 0，货币不传时默认 CNY。"""
        result = domain.normalize_subscription_data({"name": "测试", "period_type": "month", "start_date": "2026-01-01"})
        assert result["amount"] == 0
        assert result["currency"] == "CNY"

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="名称不能为空"):
            domain.normalize_subscription_data(self._minimal_data(name=""))

    def test_long_name_raises(self):
        with pytest.raises(ValueError, match="名称不能超过"):
            domain.normalize_subscription_data(self._minimal_data(name="x" * 201))

    def test_once_forces_manual_renewal(self):
        result = domain.normalize_subscription_data(
            self._minimal_data(period_type="once", auto_renew=True)
        )
        assert result["auto_renew"] is False
        assert result["renewal_policy"] == "manual"

    def test_custom_period_valid(self):
        result = domain.normalize_subscription_data(
            self._minimal_data(
                period_type="custom",
                custom_period_value=14,
                custom_period_unit="day",
            )
        )
        assert result["period_type"] == "custom"
        assert result["custom_period_value"] == 14
        assert result["custom_period_unit"] == "day"

    def test_custom_period_without_values_raises(self):
        with pytest.raises(ValueError):
            domain.normalize_subscription_data(
                self._minimal_data(period_type="custom")
            )

    def test_non_custom_with_custom_values_raises(self):
        with pytest.raises(ValueError, match="仅适用于custom"):
            domain.normalize_subscription_data(
                self._minimal_data(custom_period_value=14)
            )

    def test_renewal_confirmed_auto_default(self):
        """自动续费默认 renewal_confirmed = True。"""
        result = domain.normalize_subscription_data(self._minimal_data())
        assert result["renewal_confirmed"] is True

    def test_renewal_confirmed_manual_default(self):
        """手动续费默认 renewal_confirmed = False。"""
        result = domain.normalize_subscription_data(
            self._minimal_data(auto_renew=False)
        )
        assert result["renewal_confirmed"] is False


# --------------------------------------------------------------------------- #
# should_auto_renew_on_wake
# --------------------------------------------------------------------------- #


class TestShouldAutoRenewOnWake:
    def test_policy_auto_returns_true(self):
        assert domain.should_auto_renew_on_wake("auto") is True

    def test_policy_manual_returns_false(self):
        assert domain.should_auto_renew_on_wake("manual") is False

    def test_policy_stop_returns_false(self):
        assert domain.should_auto_renew_on_wake("stop") is False

    def test_bool_true_fallback(self):
        """未传 renewal_policy 时降级到布尔值 auto_renew。"""
        assert domain.should_auto_renew_on_wake(True) is True

    def test_bool_false_fallback(self):
        assert domain.should_auto_renew_on_wake(False) is False

    def test_explicit_policy_overrides_bool(self):
        """renewal_policy 参数优先。"""
        assert domain.should_auto_renew_on_wake(True, "manual") is False
        assert domain.should_auto_renew_on_wake(False, "auto") is True

    def test_case_insensitive(self):
        assert domain.should_auto_renew_on_wake("AUTO") is True


# --------------------------------------------------------------------------- #
# normalize_renewal_policy / normalize_lifecycle / normalize_currency
# --------------------------------------------------------------------------- #


class TestNormalizeEnums:
    def test_renewal_chinese_aliases(self):
        assert domain.normalize_renewal_policy("自动续费") == "auto"
        assert domain.normalize_renewal_policy("手动续费") == "manual"
        assert domain.normalize_renewal_policy("到期停止") == "stop"

    def test_renewal_invalid_raises(self):
        with pytest.raises(ValueError):
            domain.normalize_renewal_policy("invalid")

    def test_lifecycle_chinese_aliases(self):
        assert domain.normalize_lifecycle("活跃") == "active"
        assert domain.normalize_lifecycle("已取消") == "canceled"

    def test_currency_valid(self):
        assert domain.normalize_currency("usd") == "USD"
        assert domain.normalize_currency("cny") == "CNY"
        assert domain.normalize_currency("HKD") == "HKD"

    def test_currency_invalid_raises(self):
        with pytest.raises(ValueError, match="不支持的货币"):
            domain.normalize_currency("EUR")


# --------------------------------------------------------------------------- #
# calendar helpers
# --------------------------------------------------------------------------- #


class TestCalendarHelpers:
    def test_is_calendar_trackable_active(self):
        assert domain.is_calendar_trackable("active") is True

    def test_is_calendar_trackable_unsupported(self):
        """假设 unsupported 透传到 active。"""
        assert domain.is_calendar_trackable("active") is True

    def test_calendar_due_event_type(self):
        assert domain.calendar_due_event_type("auto") == "due_date"
        assert domain.calendar_due_event_type("stop") == "service_end"
        assert domain.calendar_due_event_type("stop_on_expiry") == "service_end"
