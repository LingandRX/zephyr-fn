"""回归测试：覆盖安全修复前未覆盖的统计、日期和导入边界。"""
from datetime import date
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "backend"))

from services import statistics as services



class ServicesRegressionTests(unittest.TestCase):
    def _daily_sub(self):
        return {
            "id": "daily",
            "name": "Daily",
            "amount": 100,
            "actual_amount": None,
            "currency": "CNY",
            "period_type": "custom",
            "custom_period_value": 1,
            "custom_period_unit": "day",
            "start_date": "2000-01-01",
            "next_due_date": "2000-01-02",
            "auto_renew": True,
            "renewal_policy": "auto",
            "lifecycle": "active",
            "updated_at": "2000-01-01T00:00:00Z",
        }

    def test_old_daily_subscription_is_counted_without_iteration_guard(self):
        sub = self._daily_sub()
        self.assertEqual(
            services._count_cycles_in_range(sub, date(2026, 8, 1), date(2026, 8, 31)),
            31,
        )

    def test_old_daily_subscription_calendar_is_generated(self):
        events = services._events_for_month(self._daily_sub(), 2026, 8)
        cycle_events = [e for e in events if e["event_type"] == "cycle_start"]
        self.assertEqual(len(cycle_events), 31)

    def test_zero_actual_amount_is_respected(self):
        sub = self._daily_sub()
        sub["actual_amount"] = 0
        self.assertEqual(services._monthly_amount(sub, "actual"), 0)

    def test_invalid_statistics_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            services.calculate_statistics("missing-user", "invalid")


if __name__ == "__main__":
    unittest.main()
