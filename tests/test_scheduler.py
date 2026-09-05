"""scheduler 调度基准测试：每日固定推送时刻的等待秒数。"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

# 让 backend 包可导入（backend 的父目录 app/ 加入 sys.path）
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from backend.services.scheduler import DEFAULT_PUSH_TIME, seconds_until_next_push  # noqa: E402


class SecondsUntilNextPushTest(unittest.TestCase):
    def test_before_push_time_same_day(self):
        now = datetime(2026, 8, 29, 8, 30, 0)
        self.assertEqual(seconds_until_next_push(now, "09:00"), 30 * 60)

    def test_after_push_time_rolls_to_next_day(self):
        now = datetime(2026, 8, 29, 12, 0, 0)
        self.assertEqual(seconds_until_next_push(now, "09:00"), 21 * 3600)

    def test_exact_push_time_rolls_to_next_day(self):
        now = datetime(2026, 8, 29, 9, 0, 0)
        self.assertEqual(seconds_until_next_push(now, "09:00"), 24 * 3600)

    def test_seconds_fraction(self):
        now = datetime(2026, 8, 29, 8, 59, 59)
        self.assertEqual(seconds_until_next_push(now, "09:00"), 1.0)

    def test_midnight_cross(self):
        now = datetime(2026, 8, 29, 23, 30, 0)
        self.assertEqual(seconds_until_next_push(now, "09:00"), 9 * 3600 + 30 * 60)

    def test_invalid_clock_falls_back_to_default(self):
        now = datetime(2026, 8, 29, 8, 0, 0)
        self.assertEqual(seconds_until_next_push(now, "bad"), 3600)

    def test_none_falls_back_to_default(self):
        now = datetime(2026, 8, 29, 8, 0, 0)
        self.assertEqual(seconds_until_next_push(now, None), 3600)

    def test_default_push_time_constant(self):
        # 默认推送时刻必须可被 parse_clock 解析为 09:00
        self.assertEqual(DEFAULT_PUSH_TIME, "09:00")


if __name__ == "__main__":
    unittest.main()
