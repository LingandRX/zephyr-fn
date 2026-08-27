"""订阅管理后端包（分层架构）。

架构分层：
- core/      : 核心业务领域逻辑（领域模型、周期推进、状态派生、输入校验）
- services/  : 业务应用服务（统计报表、通知业务、备份导入导出、定时调度）
- storage/   : 数据持久化仓储（SQLite 访问、Schema 迁移、数据 CRUD）
- utils/     : 基础设施与通用工具（通知渠道 Email/PushPlus、文件与目录 IO 工具）
- server.py  : HTTP / UDS 网关接入与路由处理
- config.py  : 运行环境与路径配置
"""
from __future__ import annotations

from . import config, core, services, storage, utils

__all__ = [
    "config",
    "core",
    "services",
    "storage",
    "utils",
]
