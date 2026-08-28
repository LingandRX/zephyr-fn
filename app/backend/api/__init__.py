"""API 蓝图层：路由与请求解析。

每个资源一个蓝图，控制器只做「取参数 → 调服务 → 包统一响应」，
业务逻辑在 services/，持久化在 storage/。
"""
from __future__ import annotations

from flask import Blueprint

from . import (
    backup,
    categories,
    logs,
    notifications,
    settings,
    statistics,
    subscriptions,
    web,
)


def register_blueprints(app) -> None:
    app.register_blueprint(subscriptions.bp)
    app.register_blueprint(categories.bp)
    app.register_blueprint(settings.bp)
    app.register_blueprint(statistics.bp)
    app.register_blueprint(backup.bp)
    app.register_blueprint(notifications.bp)
    app.register_blueprint(logs.bp)
    app.register_blueprint(web.bp)


__all__ = ["register_blueprints"]
