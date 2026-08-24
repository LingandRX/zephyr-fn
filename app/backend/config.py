"""运行环境配置：读取 fnOS 提供的 TRIM_* 环境变量，本地开发时使用默认值。

在飞牛 fnOS 上运行时，生命周期脚本会注入 TRIM_APPDEST / TRIM_PKGVAR /
TRIM_DATA_SHARE_PATHS 等环境变量，子进程（本服务）直接继承即可。
"""
from __future__ import annotations

import os
from pathlib import Path

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
        return Path(w)
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
        return Path(d)
    return data_dir() / "subscription.db"


def logs_dir() -> Path:
    return data_dir() / "logs"


def backup_dir() -> Path:
    """备份目录：优先使用 data-share 共享目录（用户可在文件管理器看到）。"""
    s = _get("SHARE_DIR")
    if s:
        return Path(s)
    raw = _get("TRIM_DATA_SHARE_PATHS")
    if raw:
        first = raw.split(":")[0]
        if first:
            return Path(first)
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
