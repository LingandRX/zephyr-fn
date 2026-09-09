"""路径解析：fnOS 环境变量 → 本地默认值。

独立于 Flask 配置类，供 server / services / tests / 中间件直接使用。

在飞牛 fnOS 上，生命周期脚本会注入 TRIM_APPDEST / TRIM_PKGVAR /
TRIM_DATA_SHARE_PATHS 等环境变量，子进程直接继承。
本地开发时回退到仓库目录结构。
"""

from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# 运行时覆盖（优先级高于环境变量，供测试 / CLI 使用）
# --------------------------------------------------------------------------- #

_OVERRIDES: dict[str, str] = {}


def override(key: str, value: str | None) -> None:
    """设置运行时路径覆盖（value=None 时清除）。"""
    if value is None:
        _OVERRIDES.pop(key, None)
    else:
        _OVERRIDES[key] = value


def _get(name: str, default: str | None = None) -> str | None:
    """读取环境变量（运行时覆盖优先）。"""
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


# --------------------------------------------------------------------------- #
# 路径辅助函数
# --------------------------------------------------------------------------- #


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
    """SQLite 数据库文件路径。"""
    d = _get("DB_PATH")
    if d:
        return _abs_path(d)
    return data_dir() / "subscription.db"


def logs_dir() -> Path:
    """日志文件目录。"""
    return data_dir() / "logs"


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
    """应用版本号。"""
    return _get("TRIM_APPVER", "0.1.1") or "0.1.1"


def sys_arch() -> str:
    """系统架构标识。"""
    return _get("TRIM_SYS_ARCH", "unknown") or "unknown"
