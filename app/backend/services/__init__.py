"""业务应用服务层（统计报表、通知业务、备份导入导出与定时调度）。

本包聚合所有应用级业务服务：
- statistics: 支出统计计算、日历事件生成
- notifications: 免打扰判断、待提醒订阅筛选、通知文案与幂等发放
- backup: 备份导出（JSON/CSV）、数据导入、SQLite 数据库合并
- scheduler: 定时任务调度器与轮询循环
"""
from __future__ import annotations

from . import backup, notifications, scheduler, statistics
from .statistics import (
    calculate_statistics,
    get_calendar_events,
)

for _k, _v in statistics.__dict__.items():
    if not _k.startswith("__"):
        globals()[_k] = _v

__all__ = [
    "backup",
    "calculate_statistics",
    "get_calendar_events",
    "notifications",
    "scheduler",
    "statistics",
]

