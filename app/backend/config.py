"""Flask 配置类（环境隔离）。

路径解析函数委托给 paths.py；通过此模块重导出以保持
``config.www_dir()`` 等调用方式不变。
"""

from __future__ import annotations

import os

# 路径函数重导出（供现有代码 config.xxx() 调用）
from .paths import (  # noqa: F401
    app_root,
    app_version,
    data_dir,
    db_path,
    gateway_prefix,
    logs_dir,
    override,
    reminder_days_override,
    sys_arch,
    www_dir,
)
from .paths import _get  # 内部使用，不导出

MAX_REQUEST_BODY_BYTES = 5 * 1024 * 1024
MAX_USER_ID_LENGTH = 128


class BaseConfig:
    """生产基线配置；环境差异通过子类覆盖。"""

    # 安全：生产环境必须通过 SECRET_KEY 环境变量注入
    SECRET_KEY = os.environ.get("SECRET_KEY") or "subscription-dev-insecure-key"

    TESTING = False
    DEBUG = False

    # 请求边界
    MAX_CONTENT_LENGTH = MAX_REQUEST_BODY_BYTES
    JSON_AS_ASCII = False

    # 本地 TCP 开发模式允许无身份头请求（回退为 local 管理员）
    ALLOW_HEADERLESS_LOCAL = False

    # SQLAlchemy
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # 数据库 URI 依赖运行时 override（--db / TRIM_PKGVAR），
    # 由应用工厂在 from_object 之后显式计算；TestingConfig 覆盖为内存库。
    SQLALCHEMY_DATABASE_URI = None
    SQLALCHEMY_ENGINE_OPTIONS = {
        # SQLite 多线程：WAL 下允许多读一写
        "connect_args": {"check_same_thread": False, "timeout": 5},
    }


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    ALLOW_HEADERLESS_LOCAL = True


class ProductionConfig(BaseConfig):
    """设备部署（fnOS 网关模式）；不开放任何调试能力。"""


class TestingConfig(BaseConfig):
    TESTING = True
    ALLOW_HEADERLESS_LOCAL = True
    # 测试库放到系统临时目录，避免污染仓库 data/
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


CONFIG_CLASSES: dict[str, type[BaseConfig]] = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config(env: str | None = None) -> type[BaseConfig]:
    """按环境选择配置类。

    env 未显式传入时：优先 ``SUBSCRIPTION_ENV``，其次根据是否在 fnOS
    设备（存在 TRIM_APPDEST）判定为 production，本地回退 development。
    """
    if env is None:
        env = os.environ.get("SUBSCRIPTION_ENV")
    if env is None:
        env = "production" if _get("TRIM_APPDEST") else "development"
    try:
        return CONFIG_CLASSES[env]
    except KeyError as exc:
        raise ValueError(f"未知运行环境: {env}（可选: {', '.join(CONFIG_CLASSES)}）") from exc
