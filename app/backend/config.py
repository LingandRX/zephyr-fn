"""运行环境配置：环境隔离 + 路径解析。

两部分职责：
1. 路径辅助函数：读取 fnOS 提供的 TRIM_* 环境变量，本地开发时使用默认值。
   （在飞牛 fnOS 上，生命周期脚本会注入 TRIM_APPDEST / TRIM_PKGVAR /
   TRIM_DATA_SHARE_PATHS 等环境变量，子进程直接继承。）
2. Flask 配置类：按环境隔离（Development / Production / Testing），
   敏感信息（SECRET_KEY）通过环境变量注入。
"""
from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# 路径解析（模块级函数，供 server / services / tests 直接使用）
# --------------------------------------------------------------------------- #

# 本地开发/测试时可手动覆盖（优先级高于环境变量）
_OVERRIDES: dict[str, str] = {}


def override(key: str, value: str | None) -> None:
    if value is None:
        _OVERRIDES.pop(key, None)
    else:
        _OVERRIDES[key] = value


def _get(name: str, default: str | None = None) -> str | None:
    if name in _OVERRIDES:
        return _OVERRIDES[name]
    value = os.environ.get(name)
    return value if value else default


def _abs_path(value: str | Path) -> Path:
    """统一解析为绝对路径。

    Flask/werkzeug 与 os 系列对相对路径的基准不一致（send_file 按
    app.root_path 拼接、mkdir 按进程 CWD 解析），相对路径会引发
    找不到文件等隐蔽问题；所有路径辅助函数一律返回绝对路径。
    """
    return Path(value).resolve()


def app_root() -> Path:
    """应用安装后的 target 目录；本地开发回退到仓库根目录。"""
    dest = _get("TRIM_APPDEST")
    if dest:
        return Path(dest)
    return Path(__file__).resolve().parent.parent.parent


def www_dir() -> Path:
    """前端静态文件目录。"""
    w = _get("WWW_DIR")
    if w:
        return _abs_path(w)
    return app_root() / "www"


def data_dir() -> Path:
    """运行数据目录（数据库、日志）。"""
    pkgvar = _get("TRIM_PKGVAR")
    if pkgvar:
        return Path(pkgvar)
    return Path(__file__).resolve().parent.parent.parent / "data"


def db_path() -> Path:
    d = _get("DB_PATH")
    if d:
        return _abs_path(d)
    return data_dir() / "subscription.db"


def logs_dir() -> Path:
    return data_dir() / "logs"


def backup_dir() -> Path:
    """备份目录：优先使用 data-share 共享目录（用户可在文件管理器看到）。"""
    s = _get("SHARE_DIR")
    if s:
        return _abs_path(s)
    raw = _get("TRIM_DATA_SHARE_PATHS")
    if raw:
        first = raw.split(":")[0]
        if first:
            return _abs_path(first)
    return data_dir() / "backups"


def reminder_days_override() -> int | None:
    """安装向导显式传入的提醒提前天数（wizard_reminder_days）。

    仅当安装/升级回调收到向导值时返回数字；否则返回 None，表示不覆盖
    数据库中的已有设置。
    """
    raw = _get("wizard_reminder_days")
    if raw is None:
        return None
    try:
        return max(0, int(raw))
    except ValueError:
        return None


def gateway_prefix() -> str:
    """统一网关注册前缀（须与 app/ui/config 的 gatewayPrefix 一致）。"""
    return _get("GATEWAY_PREFIX", "/app/subscription") or "/app/subscription"


def app_version() -> str:
    return _get("TRIM_APPVER", "0.1.1") or "0.1.1"


def sys_arch() -> str:
    return _get("TRIM_SYS_ARCH", "unknown") or "unknown"


# --------------------------------------------------------------------------- #
# Flask 配置类（环境隔离）
# --------------------------------------------------------------------------- #

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
    except KeyError:
        raise ValueError(f"未知运行环境: {env}（可选: {', '.join(CONFIG_CLASSES)}）")
