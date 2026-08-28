"""订阅管理后端包（四层架构）。

架构分层（Controller → Service → Model/Schema → Storage）：
- app.py      : 应用工厂（配置装配、扩展、中间件、错误处理、蓝图、数据库迁移）
- server.py   : 进程入口（CLI、日志、UDS/TCP 启动）
- api/        : 路由层（Blueprint，请求解析与响应封装）
- services/   : 业务层（订阅/分类/设置/统计/通知/备份/调度）
- schemas/    : 参数校验与序列化（复用 core/domain 的严格校验）
- models/     : ORM 数据实体（Flask-SQLAlchemy）
- storage/    : 数据持久化（repositories 仓储 + bootstrap 旧库升级）
- core/       : 领域逻辑与公共基础设施（domain/exceptions/response/middleware）
- utils/      : 基础设施工具（通知渠道、文件 IO）
- config.py   : 环境隔离配置与路径解析
- migrations/ : Flask-Migrate / Alembic 版本迁移
"""
from __future__ import annotations

from . import config, core, models, schemas, services, storage, utils
from .app import create_app

__all__ = [
    "config",
    "core",
    "create_app",
    "models",
    "schemas",
    "services",
    "storage",
    "utils",
]
