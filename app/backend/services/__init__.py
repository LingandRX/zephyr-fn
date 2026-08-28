"""业务应用服务层（订阅/分类/设置 CRUD、统计报表、通知、备份、定时调度）。

- subscriptions : 订阅业务（校验 → 周期推导 → 仓储编排）
- categories    : 分类业务（去重/上限校验、默认分类补种）
- settings      : 应用设置（密钥脱敏、更新编排）
- statistics    : 支出统计计算、日历事件生成
- notifications : 免打扰判断、待提醒订阅筛选、通知文案与幂等发放
- backup        : 备份导出（JSON/CSV）、数据导入、SQLite 数据库合并
- scheduler     : 定时任务调度器与轮询循环
"""
from __future__ import annotations

from . import backup, categories, notifications, scheduler, settings, statistics, subscriptions
from .statistics import (
    calculate_statistics,
    get_calendar_events,
)

__all__ = [
    "backup",
    "calculate_statistics",
    "categories",
    "get_calendar_events",
    "notifications",
    "scheduler",
    "settings",
    "statistics",
    "subscriptions",
]
