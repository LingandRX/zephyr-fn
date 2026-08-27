"""SQLite 数据访问层（持久化与仓储）。

- 单连接 + 线程锁（服务器多线程）
- 版本化迁移（db_version 表），升级时自动补迁
- 金额以「分」(amount) 整数存储；时间戳为 RFC3339 UTC 字符串
- user_id 列：按 NAS 登录用户（X-Trim-Userid）隔离订阅与分类数据
"""
from __future__ import annotations

import logging
import re
import sqlite3
import threading
import unicodedata
import uuid
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

try:
    from ..core import domain
except (ImportError, ValueError):
    from core import domain  # type: ignore[no-redef]


_lock = threading.RLock()
_logger = logging.getLogger("subscription.db")
_conn: sqlite3.Connection | None = None
_transaction_state = threading.local()

# 进程内已播种用户缓存：避免每个 API 请求都查询 seeded_users 表。
# connect() 换库时必须清空。
_seeded_users_cache: set[str] = set()

CURRENT_DB_VERSION = 11
MAX_NOTES_LENGTH = 120
MAX_CATEGORY_NAME_LEN = 20
MAX_CATEGORIES_PER_USER = 50
_CATEGORY_ILLEGAL_RE = re.compile(r'[<>"\'&]')

# app_settings 的字段定义集中维护，迁移和 SETTINGS_FIELDS 共用这份清单，
# 避免新增设置字段后忘记补 schema。
_SETTINGS_COLUMN_DEFINITIONS = {
    "dark_mode": "TEXT NOT NULL DEFAULT 'system'",
    "default_currency": "TEXT NOT NULL DEFAULT 'CNY'",
    "exchange_rate_usd": "REAL NOT NULL DEFAULT 7.2",
    "exchange_rate_hkd": "REAL NOT NULL DEFAULT 0.92",
    "notification_days": "INTEGER NOT NULL DEFAULT 7",
    "do_not_disturb_start": "TEXT",
    "do_not_disturb_end": "TEXT",
    "auto_start": "INTEGER NOT NULL DEFAULT 0",
    "tray_mode": "INTEGER NOT NULL DEFAULT 1",
    "email_enabled": "INTEGER NOT NULL DEFAULT 0",
    "smtp_host": "TEXT",
    "smtp_port": "INTEGER",
    "smtp_username": "TEXT",
    "smtp_password": "TEXT",
    "smtp_from_address": "TEXT",
    "email_template": "TEXT NOT NULL DEFAULT 'default'",
    "notification_enabled": "INTEGER NOT NULL DEFAULT 1",
    "pushplus_enabled": "INTEGER NOT NULL DEFAULT 0",
    "pushplus_token": "TEXT",
    "last_check_date": "TEXT",
    "last_rate_update": "TEXT",
}

_VALID_TABLE_NAMES = frozenset({"app_settings", "notification_logs", "subscriptions", "categories", "db_version", "seeded_users"})

# 默认分类模板（名称, 图标, 排序）。'local' 开发身份与真实 NAS 用户的
# 首次播种共用这份清单。
_DEFAULT_CATEGORY_TEMPLATES = (
    ("流媒体", "🎬", 1),
    ("云存储", "☁️", 2),
    ("AI 工具", "🤖", 3),
    ("音乐", "🎵", 4),
    ("办公", "💼", 5),
    ("开发工具", "🛠️", 6),
    ("游戏", "🎮", 7),
    ("健身", "💪", 8),
    ("电商会员", "🛒", 9),
    ("其他", "📦", 10),
)

# v9 迁移和启动时自修复共用：每个 identity 组只保留一条日志。
# sent 优先；同一优先级下保留 created_at 最新、id 最大的记录。
_NOTIFICATION_DEDUP_SQL = """
DELETE FROM notification_logs
WHERE id IN (
    SELECT doomed.id
    FROM notification_logs AS doomed
    WHERE EXISTS (
        SELECT 1
        FROM notification_logs AS winner
        WHERE winner.subscription_id = doomed.subscription_id
          AND winner.notification_date = doomed.notification_date
          AND winner.channel = doomed.channel
          AND (
              (winner.status = 'sent' AND doomed.status <> 'sent')
              OR (
                  (winner.status = 'sent' AND doomed.status = 'sent')
                  OR (winner.status <> 'sent' AND doomed.status <> 'sent')
              )
              AND (
                  winner.created_at > doomed.created_at
                  OR (winner.created_at = doomed.created_at AND winner.id > doomed.id)
              )
          )
    )
);
"""

_MIGRATIONS: list[tuple[int, str]] = [
    (1, """
CREATE TABLE IF NOT EXISTS categories (\n    id TEXT PRIMARY KEY,\n    user_id TEXT NOT NULL DEFAULT 'local',\n    name TEXT NOT NULL,\n    icon TEXT,\n    sort_order INTEGER DEFAULT 0\n);
CREATE TABLE IF NOT EXISTS subscriptions (\n    id TEXT PRIMARY KEY,\n    user_id TEXT NOT NULL DEFAULT 'local',\n    name TEXT NOT NULL,\n    amount INTEGER NOT NULL,\n    currency TEXT NOT NULL DEFAULT 'CNY',\n    actual_amount INTEGER,\n    category_id TEXT,\n    notes TEXT,\n    period_type TEXT NOT NULL,\n    custom_period_value INTEGER,\n    custom_period_unit TEXT,\n    auto_renew INTEGER NOT NULL DEFAULT 1,\n    sharing_role TEXT,\n    sharing_count INTEGER,\n    start_date TEXT NOT NULL,\n    first_payment_date TEXT,\n    next_due_date TEXT,\n    lifecycle TEXT NOT NULL DEFAULT 'active',\n    renewal_policy TEXT NOT NULL DEFAULT 'auto',\n    billing_status TEXT NOT NULL DEFAULT 'normal',\n    grace_period_ends_at TEXT,\n    sync_version INTEGER NOT NULL DEFAULT 1,\n    created_at TEXT NOT NULL,\n    updated_at TEXT NOT NULL\n);
CREATE TABLE IF NOT EXISTS app_settings (\n    id INTEGER PRIMARY KEY CHECK (id = 1),\n    dark_mode TEXT NOT NULL DEFAULT 'system',\n    default_currency TEXT NOT NULL DEFAULT 'CNY',\n    exchange_rate_usd REAL NOT NULL DEFAULT 7.2,\n    exchange_rate_hkd REAL NOT NULL DEFAULT 0.92,\n    notification_days INTEGER NOT NULL DEFAULT 7,\n    do_not_disturb_start TEXT,\n    do_not_disturb_end TEXT,\n    auto_start INTEGER NOT NULL DEFAULT 0,\n    tray_mode INTEGER NOT NULL DEFAULT 1,\n    email_enabled INTEGER NOT NULL DEFAULT 0,\n    smtp_host TEXT,\n    smtp_port INTEGER,\n    smtp_username TEXT,\n    smtp_password TEXT,\n    smtp_from_address TEXT,\n    email_template TEXT NOT NULL DEFAULT 'default',\n    created_at TEXT NOT NULL,\n    updated_at TEXT NOT NULL\n);
CREATE INDEX IF NOT EXISTS idx_sub_user ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_sub_next ON subscriptions(next_due_date);
"""),
    (2, """
CREATE TABLE IF NOT EXISTS email_logs (\n    id TEXT PRIMARY KEY,\n    to_address TEXT NOT NULL,\n    subject TEXT NOT NULL,\n    status TEXT NOT NULL DEFAULT 'pending',\n    error_message TEXT,\n    sent_at TEXT,\n    created_at TEXT NOT NULL\n);
"""),
    (3, """
CREATE TABLE IF NOT EXISTS notification_logs (\n    id TEXT PRIMARY KEY,\n    subscription_id TEXT NOT NULL,\n    notification_date TEXT NOT NULL,\n    channel TEXT NOT NULL,\n    status TEXT NOT NULL DEFAULT 'sent',\n    error_message TEXT,\n    created_at TEXT NOT NULL\n);
CREATE INDEX IF NOT EXISTS idx_notif_sub_date ON notification_logs(subscription_id, notification_date);
"""),
    (4, "ALTER TABLE app_settings ADD COLUMN notification_enabled INTEGER NOT NULL DEFAULT 1;"),
    (5, "ALTER TABLE app_settings ADD COLUMN pushplus_enabled INTEGER NOT NULL DEFAULT 0;"),
    (6, "ALTER TABLE app_settings ADD COLUMN pushplus_token TEXT;"),
    (7, "ALTER TABLE app_settings ADD COLUMN last_check_date TEXT;"),
    # v8：SETTINGS_FIELDS 中的 last_rate_update 正式落库。
    (8, "ALTER TABLE app_settings ADD COLUMN last_rate_update TEXT;"),
    # v9：清理历史重复通知，并建立数据库级幂等约束。
    (9, _NOTIFICATION_DEDUP_SQL + "\n"
        "CREATE UNIQUE INDEX IF NOT EXISTS "
        "idx_notification_logs_identity "
        "ON notification_logs(subscription_id, notification_date, channel);"),
    # v10：分类重名唯一约束（大小写不敏感）。
    (10, """
CREATE UNIQUE INDEX IF NOT EXISTS idx_cat_user_name
  ON categories(user_id, name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_cat_user_sort
  ON categories(user_id, sort_order);
"""),
    # v11：按用户播种默认分类。
    (11, """
CREATE TABLE IF NOT EXISTS seeded_users (
    user_id TEXT PRIMARY KEY,
    seeded_at TEXT NOT NULL
);
INSERT OR IGNORE INTO seeded_users (user_id, seeded_at)
SELECT user_id, strftime('%Y-%m-%dT%H:%M:%SZ', 'now') FROM (
    SELECT DISTINCT user_id FROM subscriptions
    UNION
    SELECT DISTINCT user_id FROM categories
)
WHERE user_id IS NOT NULL AND user_id <> '';
"""),
]

SUBSCRIPTION_FIELDS = (
    "name", "amount", "currency", "actual_amount", "category_id", "notes",
    "period_type", "custom_period_value", "custom_period_unit", "auto_renew",
    "sharing_role", "sharing_count", "start_date", "first_payment_date",
    "next_due_date", "lifecycle", "renewal_policy", "billing_status",
    "grace_period_ends_at",
)
SETTINGS_FIELDS = (
    "dark_mode", "default_currency", "exchange_rate_usd", "exchange_rate_hkd",
    "notification_days", "do_not_disturb_start", "do_not_disturb_end",
    "auto_start", "tray_mode", "email_enabled", "smtp_host", "smtp_port",
    "smtp_username", "smtp_password", "smtp_from_address", "email_template",
    "notification_enabled", "pushplus_enabled", "pushplus_token",
    "last_check_date", "last_rate_update",
)

_SUBSCRIPTION_COLUMNS = (
    "id", "user_id", "name", "amount", "currency", "actual_amount",
    "category_id", "notes", "period_type", "custom_period_value",
    "custom_period_unit", "auto_renew", "sharing_role", "sharing_count",
    "start_date", "first_payment_date", "next_due_date", "lifecycle",
    "renewal_policy", "billing_status", "grace_period_ends_at",
    "sync_version", "created_at", "updated_at",
)


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id() -> str:
    return uuid.uuid4().hex


# --------------------------------------------------------------------------- #
# 连接与迁移
# --------------------------------------------------------------------------- #

def connect(path: Path) -> None:
    """打开数据库、设置并发参数并执行所有待迁移版本。"""
    global _conn
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None
        _conn = sqlite3.connect(str(path), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
        _conn.execute("PRAGMA busy_timeout=5000")
        _run_migrations()
        _ensure_settings_schema()
        _ensure_notification_schema()
        _seed_default_settings()
        _seeded_users_cache.clear()
        _conn.commit()


def close() -> None:
    """关闭当前连接；测试、热重载和进程退出时可安全调用。"""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None


@contextmanager
def transaction():
    """提供可嵌套的、线程安全的数据库事务原语。"""
    conn = _require_conn()
    depth = getattr(_transaction_state, "depth", 0)
    outermost = depth == 0
    with _lock:
        if outermost:
            conn.execute("BEGIN IMMEDIATE")
        _transaction_state.depth = depth + 1
        try:
            yield conn
        except Exception:
            _transaction_state.depth = depth
            if outermost:
                conn.rollback()
            raise
        else:
            _transaction_state.depth = depth
            if outermost:
                conn.commit()


def _commit() -> None:
    conn = _require_conn()
    if getattr(_transaction_state, "depth", 0) == 0:
        conn.commit()


def _get_db_version() -> int:
    conn = _require_conn()
    row = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='db_version'"
    ).fetchone()
    if row[0] == 0:
        return 0
    row = conn.execute("SELECT version FROM db_version WHERE id=1").fetchone()
    return int(row[0]) if row else 0


def _column_exists(table: str, column: str) -> bool:
    if table not in _VALID_TABLE_NAMES:
        raise ValueError(f"非法表名: {table}")
    conn = _require_conn()
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def _ensure_settings_schema() -> None:
    """修复版本号与实际 schema 不一致的旧数据库。"""
    conn = _require_conn()
    for column, definition in _SETTINGS_COLUMN_DEFINITIONS.items():
        if not _column_exists("app_settings", column):
            conn.execute(f"ALTER TABLE app_settings ADD COLUMN {column} {definition}")


def _ensure_notification_schema() -> None:
    """修复通知日志 schema，并保证旧数据库也具备幂等写入能力。"""
    conn = _require_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notification_logs (
            id TEXT PRIMARY KEY,
            subscription_id TEXT NOT NULL,
            notification_date TEXT NOT NULL,
            channel TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'sent',
            error_message TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute(_NOTIFICATION_DEDUP_SQL)

    index_name = "idx_notification_logs_identity"
    expected_columns = ["subscription_id", "notification_date", "channel"]
    existing = conn.execute("PRAGMA index_list(notification_logs)").fetchall()
    for index in existing:
        if index[1] != index_name:
            continue
        columns = [row[2] for row in conn.execute(
            f'PRAGMA index_info("{index_name}")'
        ).fetchall()]
        is_unique = bool(index[2])
        is_partial = len(index) > 5 and bool(index[5])
        if not (is_unique and not is_partial and columns == expected_columns):
            conn.execute(f'DROP INDEX "{index_name}"')
        break

    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_notification_logs_identity "
        "ON notification_logs(subscription_id, notification_date, channel)"
    )
    conn.execute("DROP TRIGGER IF EXISTS trg_notification_logs_reuse_failed")


def _dedupe_categories_py(conn: sqlite3.Connection) -> None:
    """按归一化名称去重分类，保留 rowid 最小的。"""
    rows = conn.execute(
        "SELECT id, user_id, name FROM categories ORDER BY rowid ASC"
    ).fetchall()
    keep: dict[tuple[str, str], str] = {}
    doomed: list[tuple[str, str]] = []
    for r in rows:
        key = (r["user_id"], _normalize_category_name(r["name"]).lower())
        kept = keep.get(key)
        if kept is None:
            keep[key] = r["id"]
        else:
            doomed.append((r["id"], kept))
    for cat_id, kept_id in doomed:
        conn.execute(
            "UPDATE subscriptions SET category_id=?, updated_at=? WHERE category_id=?",
            (kept_id, now_utc(), cat_id),
        )
        conn.execute("DELETE FROM categories WHERE id=?", (cat_id,))


def _ensure_category_schema() -> None:
    conn = _require_conn()
    try:
        conn.execute("SELECT 1 FROM categories LIMIT 1")
    except sqlite3.OperationalError:
        return
    _dedupe_categories_py(conn)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_cat_user_name "
        "ON categories(user_id, name COLLATE NOCASE)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cat_user_sort "
        "ON categories(user_id, sort_order)"
    )


def _seed_default_categories() -> None:
    conn = _require_conn()
    row = conn.execute(
        "SELECT COUNT(DISTINCT user_id) FROM categories"
    ).fetchone()
    if row[0] > 0:
        return
    for name, icon, sort_order in _DEFAULT_CATEGORY_TEMPLATES:
        conn.execute(
            "INSERT OR IGNORE INTO categories "
            "(id, user_id, name, icon, sort_order) VALUES (?,?,?,?,?)",
            (new_id(), "local", name, icon, sort_order),
        )
    conn.execute(
        "INSERT OR IGNORE INTO seeded_users (user_id, seeded_at) VALUES (?,?)",
        ("local", now_utc()),
    )
    _logger.info("seeded %d default categories", len(_DEFAULT_CATEGORY_TEMPLATES))


def ensure_default_categories_for_user(user_id: str) -> bool:
    target = str(user_id or "").strip()
    if not target or target in _seeded_users_cache:
        return False
    conn = _require_conn()
    with _lock:
        if target in _seeded_users_cache:
            return False
        marked = conn.execute(
            "SELECT 1 FROM seeded_users WHERE user_id=?", (target,)
        ).fetchone()
        if marked:
            _seeded_users_cache.add(target)
            return False
        for name, icon, sort_order in _DEFAULT_CATEGORY_TEMPLATES:
            conn.execute(
                "INSERT OR IGNORE INTO categories "
                "(id, user_id, name, icon, sort_order) VALUES (?,?,?,?,?)",
                (new_id(), target, name, icon, sort_order),
            )
        conn.execute(
            "INSERT OR IGNORE INTO seeded_users (user_id, seeded_at) VALUES (?,?)",
            (target, now_utc()),
        )
        _commit()
        _seeded_users_cache.add(target)
    _logger.info("seeded default categories for user %s", target)
    return True


def _run_migrations() -> None:
    conn = _require_conn()
    conn.execute(
        "CREATE TABLE IF NOT EXISTS db_version "
        "(id INTEGER PRIMARY KEY CHECK (id=1), version INTEGER NOT NULL)"
    )
    version = _get_db_version()
    if version > CURRENT_DB_VERSION:
        raise RuntimeError(
            f"数据库版本 {version} 高于当前后端支持的版本 {CURRENT_DB_VERSION}"
        )

    for target_version, sql in sorted(_MIGRATIONS):
        if version >= target_version:
            continue
        if target_version == 10:
            _dedupe_categories_py(conn)
        statements = [s.strip() for s in sql.split(";") if s.strip()]
        for stmt in statements:
            lower = stmt.lower()
            if lower.startswith("alter table"):
                tokens = stmt.split()
                table = tokens[2] if len(tokens) > 2 else ""
                column = tokens[5] if len(tokens) > 5 and tokens[3].lower() == "add" \
                    and tokens[4].lower() == "column" else ""
                if table and column and _column_exists(table.strip(), column.strip()):
                    continue
            conn.execute(stmt)
        conn.execute(
            "INSERT INTO db_version (id, version) VALUES (1, ?) "
            "ON CONFLICT(id) DO UPDATE SET version=excluded.version",
            (target_version,),
        )
        version = target_version

    _ensure_settings_schema()
    _ensure_category_schema()
    _seed_default_categories()
    conn.execute(
        "INSERT INTO db_version (id, version) VALUES (1, ?) "
        "ON CONFLICT(id) DO UPDATE SET version=excluded.version",
        (CURRENT_DB_VERSION,),
    )


def _seed_default_settings() -> None:
    conn = _require_conn()
    now = now_utc()
    try:
        from .. import config
        days = config.reminder_days_override()
    except Exception:
        try:
            import config
            days = config.reminder_days_override()
        except Exception:
            days = None
    if days is not None:
        conn.execute(
            "INSERT INTO app_settings (id, notification_days, created_at, updated_at) "
            "VALUES (1, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "notification_days=excluded.notification_days, "
            "updated_at=excluded.updated_at",
            (days, now, now),
        )
    else:
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (id, created_at, updated_at) VALUES (1, ?, ?)",
            (now, now),
        )


def _require_conn() -> sqlite3.Connection:
    if _conn is None:
        raise RuntimeError("database not initialized")
    return _conn


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #

def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).lower() in ("1", "true", "yes", "on")


def _date_value(value: Any) -> str | None:
    return domain.normalize_date(value, "日期")


def _normalize_notes(value: Any) -> str | None:
    notes = str(value or "").strip()
    if len(notes) > MAX_NOTES_LENGTH:
        raise ValueError(f"备注不能超过{MAX_NOTES_LENGTH}字")
    return notes or None


def _optional_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _normalize_sharing_count(value: Any) -> int | None:
    return domain.normalize_non_negative_int(value, "共享人数", allow_none=True)


def _row_to_sub(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["auto_renew"] = bool(data["auto_renew"])
    return data


def _row_to_settings(row: sqlite3.Row) -> dict:
    data = dict(row)
    for key in ("auto_start", "tray_mode", "email_enabled",
                "notification_enabled", "pushplus_enabled"):
        data[key] = bool(data[key])
    return data


def _reject_explicit_blank(data: Mapping[str, Any], fields: tuple[str, ...]) -> None:
    for field in fields:
        if field in data and data[field] is None:
            raise ValueError(f"{field}不能为空")
        if field in data and isinstance(data[field], str) and not data[field].strip():
            raise ValueError(f"{field}不能为空")


def _derive_next_due(normalized: Mapping[str, Any]) -> str | None:
    if normalized["period_type"] == "once":
        return None
    if normalized.get("next_due_date"):
        return normalized["next_due_date"]
    next_due = domain.add_one_period(
        date.fromisoformat(normalized["start_date"]),
        normalized["period_type"],
        normalized.get("custom_period_value"),
        normalized.get("custom_period_unit"),
    )
    return next_due.isoformat() if next_due else None


def _normalize_new_subscription(user_id: str, data: Mapping[str, Any]) -> dict:
    if not isinstance(data, Mapping):
        raise ValueError("订阅数据必须是对象")
    _reject_explicit_blank(
        data,
        ("name", "amount", "currency", "period_type", "auto_renew", "start_date",
         "lifecycle"),
    )
    normalized = domain.normalize_subscription_data(
        data,
        defaults={
            "amount": 0,
            "currency": "CNY",
            "period_type": "month",
            "auto_renew": True,
            "lifecycle": "active",
            "billing_status": "normal",
            "start_date": date.today().isoformat(),
        },
    )
    normalized["next_due_date"] = _derive_next_due(normalized)
    timestamp = now_utc()
    return {
        "id": new_id(),
        "user_id": str(user_id or "local"),
        "name": normalized["name"],
        "amount": normalized["amount"],
        "currency": normalized["currency"],
        "actual_amount": normalized["actual_amount"],
        "category_id": _optional_text(data.get("category_id")),
        "notes": _normalize_notes(data.get("notes")),
        "period_type": normalized["period_type"],
        "custom_period_value": normalized["custom_period_value"],
        "custom_period_unit": normalized["custom_period_unit"],
        "auto_renew": int(normalized["auto_renew"]),
        "sharing_role": _optional_text(data.get("sharing_role")),
        "sharing_count": _normalize_sharing_count(data.get("sharing_count")),
        "start_date": normalized["start_date"],
        "first_payment_date": normalized["first_payment_date"],
        "next_due_date": normalized["next_due_date"],
        "lifecycle": normalized["lifecycle"],
        "renewal_policy": normalized["renewal_policy"],
        "billing_status": normalized["billing_status"],
        "grace_period_ends_at": normalized["grace_period_ends_at"],
        "sync_version": 1,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def _normalize_raw_subscription(
    sub: Mapping[str, Any],
    user_id: str | None = None,
    *,
    preserve_id: bool = False,
) -> dict:
    if not isinstance(sub, Mapping):
        raise ValueError("订阅数据必须是对象")
    owner = str(user_id if user_id is not None else sub.get("user_id", "local") or "local")
    _reject_explicit_blank(
        sub,
        ("name", "amount", "currency", "period_type", "auto_renew", "start_date",
         "lifecycle"),
    )
    normalized = domain.normalize_subscription_data(
        sub,
        defaults={
            "amount": 0,
            "currency": "CNY",
            "period_type": "month",
            "auto_renew": True,
            "lifecycle": "active",
            "billing_status": "normal",
            "start_date": date.today().isoformat(),
        },
    )
    normalized["next_due_date"] = _derive_next_due(normalized)
    raw_id = str(sub.get("id") or "").strip()
    if not raw_id:
        raw_id = new_id()
    if not preserve_id:
        raw_id = raw_id
    sync_version = domain.normalize_positive_int(
        sub.get("sync_version", 1), "同步版本"
    )
    timestamp = now_utc()
    created_at = str(sub.get("created_at") or timestamp)
    updated_at = str(sub.get("updated_at") or timestamp)
    return {
        "id": raw_id,
        "user_id": owner,
        "name": normalized["name"],
        "amount": normalized["amount"],
        "currency": normalized["currency"],
        "actual_amount": normalized["actual_amount"],
        "category_id": _optional_text(sub.get("category_id")),
        "notes": _normalize_notes(sub.get("notes")),
        "period_type": normalized["period_type"],
        "custom_period_value": normalized["custom_period_value"],
        "custom_period_unit": normalized["custom_period_unit"],
        "auto_renew": int(normalized["auto_renew"]),
        "sharing_role": _optional_text(sub.get("sharing_role")),
        "sharing_count": _normalize_sharing_count(sub.get("sharing_count")),
        "start_date": normalized["start_date"],
        "first_payment_date": normalized["first_payment_date"],
        "next_due_date": normalized["next_due_date"],
        "lifecycle": normalized["lifecycle"],
        "renewal_policy": normalized["renewal_policy"],
        "billing_status": normalized["billing_status"],
        "grace_period_ends_at": normalized["grace_period_ends_at"],
        "sync_version": sync_version,
        "created_at": created_at,
        "updated_at": updated_at,
    }


# --------------------------------------------------------------------------- #
# 订阅 CRUD
# --------------------------------------------------------------------------- #

def get_all_subscriptions(user_id: str) -> list[dict]:
    conn = _require_conn()
    with _lock:
        rows = conn.execute(
            "SELECT * FROM subscriptions WHERE user_id=? ORDER BY next_due_date ASC, name ASC",
            (user_id,),
        ).fetchall()
    return [_row_to_sub(r) for r in rows]


def get_subscription_by_id(sub_id: str, user_id: str) -> dict | None:
    conn = _require_conn()
    with _lock:
        row = conn.execute(
            "SELECT * FROM subscriptions WHERE id=? AND user_id=?", (sub_id, user_id)
        ).fetchone()
    return _row_to_sub(row) if row else None


def create_subscription(user_id: str, data: dict) -> dict:
    conn = _require_conn()
    sub = _normalize_new_subscription(user_id, data)
    cols = list(sub.keys())
    with _lock:
        conn.execute(
            f"INSERT INTO subscriptions ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            [sub[c] for c in cols],
        )
        _commit()
    result = get_subscription_by_id(sub["id"], sub["user_id"])
    if result is None:
        raise RuntimeError("订阅创建后无法读取")
    return result


def _normalize_update_subscription(
    current: Mapping[str, Any], data: Mapping[str, Any]
) -> tuple[dict[str, Any], set[str]]:
    if not isinstance(data, Mapping):
        raise ValueError("订阅数据必须是对象")
    requested = {field for field in SUBSCRIPTION_FIELDS if field in data}
    if not requested:
        return dict(current), set()

    _reject_explicit_blank(
        data,
        ("name", "amount", "currency", "period_type", "auto_renew", "lifecycle"),
    )
    if "renewal_policy" in data and (
        data["renewal_policy"] is None
        or (isinstance(data["renewal_policy"], str) and not data["renewal_policy"].strip())
    ):
        raise ValueError("续费策略不能为空")
    if "start_date" in data and data["start_date"] is None:
        raise ValueError("开始日期不能为空")
    if "start_date" in data and isinstance(data["start_date"], str) \
            and not data["start_date"].strip():
        raise ValueError("开始日期不能为空")

    candidate: dict[str, Any] = {
        field: current.get(field)
        for field in (
            "name", "amount", "currency", "actual_amount", "period_type",
            "custom_period_value", "custom_period_unit", "auto_renew",
            "start_date", "first_payment_date", "next_due_date", "lifecycle",
            "renewal_policy", "billing_status", "grace_period_ends_at",
        )
    }
    for field in requested:
        if field in candidate:
            candidate[field] = data[field]

    effective_period = domain.normalize_period_type(candidate.get("period_type"))
    update_auto = (
        domain.normalize_bool(data["auto_renew"], "自动续费")
        if "auto_renew" in data else None
    )
    update_policy = data.get("renewal_policy") if "renewal_policy" in data else None
    effective_auto, effective_policy = domain.resolve_renewal_on_update(
        bool(current.get("auto_renew")),
        str(current.get("renewal_policy") or "manual"),
        update_auto,
        update_policy,
        period_type=effective_period,
    )
    candidate["auto_renew"] = effective_auto
    candidate["renewal_policy"] = effective_policy

    if effective_period != "custom":
        if any(
            field in data and data[field] not in (None, "")
            for field in ("custom_period_value", "custom_period_unit")
        ):
            raise ValueError("custom_period_value/custom_period_unit仅适用于custom周期")
        candidate["custom_period_value"] = None
        candidate["custom_period_unit"] = None

    normalized = domain.normalize_subscription_data(candidate)
    requested_period_fields = {
        "period_type", "custom_period_value", "custom_period_unit"
    }
    period_changed = normalized["period_type"] != current.get("period_type")
    custom_changed = any(field in data for field in requested_period_fields)
    anchor_changed = "start_date" in data
    explicit_next_due = "next_due_date" in data
    next_due_needs_recompute = period_changed or custom_changed or anchor_changed

    if normalized["period_type"] == "once":
        normalized["next_due_date"] = None
    elif next_due_needs_recompute and (
        not explicit_next_due or data.get("next_due_date") in (None, "")
    ):
        normalized["next_due_date"] = _derive_next_due(normalized)

    return normalized, requested


def update_subscription(sub_id: str, user_id: str, data: dict) -> dict | None:
    conn = _require_conn()
    current = get_subscription_by_id(sub_id, user_id)
    if current is None:
        return None

    normalized, requested = _normalize_update_subscription(current, data)
    if not requested:
        return current

    updates: dict[str, Any] = {}
    for field in requested:
        if field in normalized:
            updates[field] = normalized[field]
        elif field == "notes":
            updates[field] = _normalize_notes(data[field])
        elif field == "category_id":
            updates[field] = _optional_text(data[field])
        elif field == "sharing_role":
            updates[field] = _optional_text(data[field])
        elif field == "sharing_count":
            updates[field] = _normalize_sharing_count(data[field])

    period_changed = normalized["period_type"] != current.get("period_type")
    custom_changed = any(
        field in data for field in ("period_type", "custom_period_value", "custom_period_unit")
    )
    if period_changed or custom_changed:
        updates["period_type"] = normalized["period_type"]
        updates["custom_period_value"] = normalized["custom_period_value"]
        updates["custom_period_unit"] = normalized["custom_period_unit"]

    if "auto_renew" in data or "renewal_policy" in data or period_changed:
        updates["auto_renew"] = int(normalized["auto_renew"])
        updates["renewal_policy"] = normalized["renewal_policy"]

    if normalized["period_type"] == "once":
        updates["next_due_date"] = None
    elif (
        (period_changed or custom_changed or "start_date" in data)
        and ("next_due_date" not in data or data.get("next_due_date") in (None, ""))
    ):
        updates["next_due_date"] = _derive_next_due(normalized)

    if not updates:
        return current

    updates["updated_at"] = now_utc()
    sets = ",".join(f"{c}=?" for c in updates)
    with _lock:
        cur = conn.execute(
            f"UPDATE subscriptions SET {sets} WHERE id=? AND user_id=?",
            [updates[c] for c in updates] + [sub_id, user_id],
        )
        _commit()
    if cur.rowcount == 0:
        return None
    return get_subscription_by_id(sub_id, user_id)


def delete_subscription(sub_id: str, user_id: str) -> bool:
    conn = _require_conn()
    with _lock:
        cur = conn.execute(
            "DELETE FROM subscriptions WHERE id=? AND user_id=?", (sub_id, user_id)
        )
        _commit()
    return cur.rowcount > 0


def renew_subscription(sub_id: str, user_id: str) -> dict | None:
    """续费：把 next_due_date 推进到下一期（一次性订阅不支持）。"""
    conn = _require_conn()
    current = get_subscription_by_id(sub_id, user_id)
    if current is None or current["period_type"] == "once":
        return None
    due = date.fromisoformat(current["next_due_date"] or current["start_date"])
    nxt = domain.add_one_period(
        due, current["period_type"], current["custom_period_value"],
        current["custom_period_unit"],
    )
    if nxt is None:
        return None
    with _lock:
        conn.execute(
            "UPDATE subscriptions SET next_due_date=?, lifecycle='active', "
            "billing_status='normal', updated_at=? WHERE id=? AND user_id=?",
            (nxt.isoformat(), now_utc(), sub_id, user_id),
        )
        _commit()
    return get_subscription_by_id(sub_id, user_id)


# --------------------------------------------------------------------------- #
# 分类 CRUD
# --------------------------------------------------------------------------- #

def _normalize_category_name(name: Any) -> str:
    raw = str(name or "")
    norm = unicodedata.normalize("NFC", raw).strip()
    converted = []
    for ch in norm:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            converted.append(chr(code - 0xFEE0))
        elif code == 0x3000:
            converted.append(" ")
        else:
            converted.append(ch)
    return "".join(converted).strip()


def _validate_category_name(name: Any, user_id: str, exclude_id: str | None = None) -> str:
    normalized = _normalize_category_name(name)
    if not normalized:
        raise ValueError("分类名称不能为空")
    if len([*normalized]) > MAX_CATEGORY_NAME_LEN:
        raise ValueError(f"分类名称最多{MAX_CATEGORY_NAME_LEN}字")
    if _CATEGORY_ILLEGAL_RE.search(normalized):
        raise ValueError("分类名称不能包含 < > \" ' &")
    conn = _require_conn()
    rows = conn.execute("SELECT id, name FROM categories WHERE user_id=?", (user_id,)).fetchall()
    low = normalized.lower()
    for r in rows:
        if exclude_id and r["id"] == exclude_id:
            continue
        if _normalize_category_name(r["name"]).lower() == low:
            raise ValueError("分类已存在")
    if exclude_id is None:
        cnt = conn.execute("SELECT COUNT(*) FROM categories WHERE user_id=?", (user_id,)).fetchone()[0]
        if cnt >= MAX_CATEGORIES_PER_USER:
            raise ValueError(f"分类数量已达上限({MAX_CATEGORIES_PER_USER})")
    return normalized


def _validate_category_icon(icon: Any) -> str | None:
    if icon is None or str(icon).strip() == "":
        return None
    ic = str(icon).strip()
    if len([*ic]) > 2:
        raise ValueError("图标限1-2个emoji")
    if re.fullmatch(r"[a-zA-Z0-9]+", ic):
        raise ValueError("图标请使用 emoji，如 \U0001f3ac")
    return [*ic][0]


def get_all_categories(user_id: str) -> list[dict]:
    conn = _require_conn()
    with _lock:
        rows = conn.execute(
            "SELECT * FROM categories WHERE user_id=? ORDER BY sort_order ASC, name ASC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def create_category(user_id: str, data: dict) -> dict:
    conn = _require_conn()
    normalized_name = _validate_category_name(data.get("name"), user_id)
    icon = _validate_category_icon(data.get("icon"))
    cat_id = new_id()
    with _lock:
        if conn.execute(
            "SELECT 1 FROM categories WHERE user_id=? AND name=? COLLATE NOCASE",
            (user_id, normalized_name),
        ).fetchone():
            raise ValueError("分类已存在")
        try:
            conn.execute(
                "INSERT INTO categories (id, user_id, name, icon, sort_order) VALUES (?,?,?,?,?)",
                (cat_id, user_id, normalized_name, icon, _to_int(data.get("sort_order"), 0)),
            )
        except sqlite3.IntegrityError as e:
            if "idx_cat_user_name" in str(e) or "UNIQUE" in str(e):
                raise ValueError("分类已存在") from e
            raise
        _commit()
        _logger.info("create_category user=%s name=%s id=%s", user_id, normalized_name, cat_id[:8])
    row = conn.execute("SELECT * FROM categories WHERE id=?", (cat_id,)).fetchone()
    return dict(row)


def update_category(cat_id: str, user_id: str, data: dict) -> dict | None:
    conn = _require_conn()
    with _lock:
        row = conn.execute(
            "SELECT * FROM categories WHERE id=? AND user_id=?", (cat_id, user_id)
        ).fetchone()
        if row is None:
            return None
        updates: dict = {}
        if "name" in data:
            normalized = _validate_category_name(data.get("name"), user_id, exclude_id=cat_id)
            updates["name"] = normalized
        if "icon" in data:
            updates["icon"] = _validate_category_icon(data.get("icon"))
        if "sort_order" in data:
            updates["sort_order"] = _to_int(data.get("sort_order"), 0)
        if updates:
            sets = ",".join(f"{c}=?" for c in updates)
            try:
                conn.execute(
                    f"UPDATE categories SET {sets} WHERE id=? AND user_id=?",
                    [updates[c] for c in updates] + [cat_id, user_id],
                )
            except sqlite3.IntegrityError as e:
                if "idx_cat_user_name" in str(e) or "UNIQUE" in str(e):
                    raise ValueError("分类已存在") from e
                raise
            _commit()
            _logger.info("update_category user=%s id=%s fields=%s", user_id, cat_id[:8], list(updates.keys()))
        row = conn.execute("SELECT * FROM categories WHERE id=?", (cat_id,)).fetchone()
    return dict(row)


def delete_category(cat_id: str, user_id: str) -> bool:
    conn = _require_conn()
    with _lock:
        conn.execute(
            "UPDATE subscriptions SET category_id=NULL, updated_at=? WHERE category_id=? AND user_id=?",
            (now_utc(), cat_id, user_id),
        )
        cur = conn.execute(
            "DELETE FROM categories WHERE id=? AND user_id=?", (cat_id, user_id)
        )
        _commit()
        if cur.rowcount:
            _logger.info("delete_category user=%s id=%s", user_id, cat_id[:8])
    return cur.rowcount > 0


# --------------------------------------------------------------------------- #
# 设置
# --------------------------------------------------------------------------- #

_SECRET_SETTING_FIELDS = frozenset({"smtp_password", "pushplus_token"})
_SECRET_MASK_EXACT = frozenset({
    "***", "******", "********", "**********", "************",
    "••••", "••••••", "••••••••", "[redacted]", "[已配置]",
    "已配置", "configured",
})


def is_secret_placeholder(value: Any) -> bool:
    """判断设置请求中的值是否表示“保持原密钥”。"""
    if value is None:
        return True
    text = str(value).strip()
    if not text:
        return True
    lowered = text.lower()
    if lowered in _SECRET_MASK_EXACT:
        return True
    if "已配置" in text or lowered in {"redacted", "masked"}:
        return True
    mask_chars = {"*", "•", "·", "●"}
    return len(text) >= 3 and all(char in mask_chars for char in text)


def get_app_settings() -> dict:
    conn = _require_conn()
    with _lock:
        row = conn.execute("SELECT * FROM app_settings WHERE id=1").fetchone()
    return _row_to_settings(row)


def update_app_settings(data: dict) -> dict:
    conn = _require_conn()
    updates: dict = {}
    cleared_fields = {
        field for field in _SECRET_SETTING_FIELDS
        if data.get(f"{field}_clear")
    }
    for field in cleared_fields:
        updates[field] = None
    for field in SETTINGS_FIELDS:
        if field not in data or field in cleared_fields:
            continue
        value = data[field]
        if field in _SECRET_SETTING_FIELDS and is_secret_placeholder(value):
            continue
        if field in ("exchange_rate_usd", "exchange_rate_hkd"):
            try:
                updates[field] = float(value)
            except (TypeError, ValueError):
                continue
        elif field in ("notification_days", "smtp_port"):
            updates[field] = _to_int(value, 0) if value not in (None, "") else None
        elif field in ("auto_start", "tray_mode", "email_enabled",
                       "notification_enabled", "pushplus_enabled"):
            updates[field] = int(_to_bool(value))
        elif field == "smtp_password":
            updates[field] = str(value) if value else None
        else:
            updates[field] = str(value) if value not in (None, "") else None
    if not updates:
        return get_app_settings()
    updates["updated_at"] = now_utc()
    sets = ",".join(f"{c}=?" for c in updates)
    with _lock:
        conn.execute(
            f"UPDATE app_settings SET {sets} WHERE id=1",
            [updates[c] for c in updates],
        )
        _commit()
    return get_app_settings()


# --------------------------------------------------------------------------- #
# 通知 / 邮件日志
# --------------------------------------------------------------------------- #

def has_channel_notified_today(subscription_id: str, channel: str) -> bool:
    conn = _require_conn()
    today = date.today().isoformat()
    with _lock:
        row = conn.execute(
            "SELECT COUNT(*) FROM notification_logs "
            "WHERE subscription_id=? AND notification_date=? AND channel=? AND status='sent'",
            (subscription_id, today, channel),
        ).fetchone()
    return row[0] > 0


def log_notification(subscription_id: str, channel: str, status: str,
                     error_message: str | None = None) -> None:
    """幂等记录通知结果。"""
    notification_date = date.today().isoformat()
    created_at = now_utc()
    incoming_status = str(status or "").strip().lower() or "failed"

    with transaction() as tx:
        tx.execute(
            "INSERT INTO notification_logs (id, subscription_id, notification_date, "
            "channel, status, error_message, created_at) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(subscription_id, notification_date, channel) DO UPDATE SET "
            "status=CASE WHEN notification_logs.status='sent' THEN 'sent' "
            "           ELSE excluded.status END, "
            "error_message=CASE WHEN notification_logs.status='sent' "
            "                 THEN notification_logs.error_message "
            "                 WHEN excluded.status='sent' THEN NULL "
            "                 ELSE excluded.error_message END, "
            "created_at=CASE WHEN notification_logs.status='sent' "
            "               THEN notification_logs.created_at "
            "               ELSE excluded.created_at END",
            (new_id(), subscription_id, notification_date, channel,
             incoming_status, error_message, created_at),
        )


def log_email(to_address: str, subject: str, status: str,
              error_message: str | None = None) -> None:
    conn = _require_conn()
    with _lock:
        conn.execute(
            "INSERT INTO email_logs (id, to_address, subject, status, "
            "error_message, sent_at, created_at) VALUES (?,?,?,?,?,?,?)",
            (new_id(), to_address, subject, status, error_message,
             now_utc() if status == "sent" else None, now_utc()),
        )
        _commit()


# --------------------------------------------------------------------------- #
# 备份辅助（全量读取，供导出/合并使用）
# --------------------------------------------------------------------------- #

def get_all_subscriptions_raw(user_id: str | None = None) -> list[dict]:
    """读取原始订阅；传入 user_id 时只返回该用户数据。"""
    conn = _require_conn()
    with _lock:
        if user_id is None:
            rows = conn.execute("SELECT * FROM subscriptions ORDER BY id").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM subscriptions WHERE user_id=? ORDER BY id",
                (user_id,),
            ).fetchall()
    return [_row_to_sub(r) for r in rows]


def get_all_subscriptions_scoped(user_id: str) -> list[dict]:
    return get_all_subscriptions_raw(user_id)


def get_all_categories_raw(user_id: str | None = None) -> list[dict]:
    """读取原始分类；传入 user_id 时只返回该用户数据。"""
    conn = _require_conn()
    with _lock:
        if user_id is None:
            rows = conn.execute("SELECT * FROM categories ORDER BY id").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM categories WHERE user_id=? ORDER BY id",
                (user_id,),
            ).fetchall()
    return [dict(r) for r in rows]


def get_all_categories_scoped(user_id: str) -> list[dict]:
    return get_all_categories_raw(user_id)


def get_subscription_dedup_keys(user_id: str | None = None) -> set:
    """去重键：名称|金额|周期类型。"""
    conn = _require_conn()
    with _lock:
        if user_id is not None:
            rows = conn.execute(
                "SELECT name, amount, period_type FROM subscriptions WHERE user_id=?",
                (user_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT name, amount, period_type FROM subscriptions"
            ).fetchall()
    return {f"{r['name']}|{r['amount']}|{r['period_type']}".lower() for r in rows}


def _insert_subscription_row(conn: sqlite3.Connection, sub: Mapping[str, Any]) -> None:
    values = [sub[column] for column in _SUBSCRIPTION_COLUMNS]
    placeholders = ",".join("?" for _ in _SUBSCRIPTION_COLUMNS)
    conn.execute(
        f"INSERT INTO subscriptions ({','.join(_SUBSCRIPTION_COLUMNS)}) "
        f"VALUES ({placeholders})",
        values,
    )


def insert_subscription_raw(
    sub: Mapping[str, Any], user_id: str | None = None
) -> dict:
    """安全插入外部订阅行，绝不覆盖已有 id。"""
    conn = _require_conn()
    normalized = _normalize_raw_subscription(sub, user_id)
    owner = normalized["user_id"]
    with _lock:
        while True:
            try:
                _insert_subscription_row(conn, normalized)
                break
            except sqlite3.IntegrityError:
                if conn.execute(
                    "SELECT 1 FROM subscriptions WHERE id=?",
                    (normalized["id"],),
                ).fetchone():
                    normalized["id"] = new_id()
                    continue
                raise
        _commit()
    result = get_subscription_by_id(normalized["id"], owner)
    if result is None:
        raise RuntimeError("原始订阅插入后无法读取")
    return result


def insert_subscription_raw_scoped(user_id: str, sub: Mapping[str, Any]) -> dict:
    return insert_subscription_raw(sub, user_id=user_id)


def insert_category_raw(cat: Mapping[str, Any], user_id: str | None = None) -> bool:
    """安全插入外部分类；id 冲突时忽略，不覆盖任何用户的分类。"""
    conn = _require_conn()
    if not isinstance(cat, Mapping):
        raise ValueError("分类数据必须是对象")
    cat_id = str(cat.get("id") or "").strip()
    name = str(cat.get("name") or "未分类").strip() or "未分类"
    if not cat_id:
        raise ValueError("分类 id 不能为空")
    owner = str(user_id if user_id is not None else cat.get("user_id", "local") or "local")
    with _lock:
        cur = conn.execute(
            "INSERT OR IGNORE INTO categories (id, user_id, name, icon, sort_order) "
            "VALUES (?,?,?,?,?)",
            (cat_id, owner, name, cat.get("icon"),
             _to_int(cat.get("sort_order"), 0)),
        )
        _commit()
    return cur.rowcount > 0


def insert_category_raw_scoped(user_id: str, cat: Mapping[str, Any]) -> bool:
    return insert_category_raw(cat, user_id=user_id)


def replace_subscription_raw(
    sub: Mapping[str, Any], user_id: str | None = None
) -> bool:
    """按 owner 安全替换订阅行，不允许跨用户覆盖。"""
    conn = _require_conn()
    if not isinstance(sub, Mapping):
        raise ValueError("订阅数据必须是对象")
    normalized = _normalize_raw_subscription(sub, user_id, preserve_id=True)
    owner = normalized["user_id"]
    sub_id = normalized["id"]
    with _lock:
        existing = conn.execute(
            "SELECT user_id FROM subscriptions WHERE id=?", (sub_id,)
        ).fetchone()
        if existing and existing["user_id"] != owner:
            return False
        if existing:
            assignments = ",".join(
                f"{column}=?" for column in _SUBSCRIPTION_COLUMNS
                if column not in ("id", "user_id")
            )
            columns = [
                column for column in _SUBSCRIPTION_COLUMNS
                if column not in ("id", "user_id")
            ]
            conn.execute(
                f"UPDATE subscriptions SET {assignments} WHERE id=? AND user_id=?",
                [normalized[column] for column in columns] + [sub_id, owner],
            )
        else:
            _insert_subscription_row(conn, normalized)
        _commit()
    return True


def replace_subscription_raw_scoped(user_id: str, sub: Mapping[str, Any]) -> bool:
    return replace_subscription_raw(sub, user_id=user_id)


def export_db_copy(target_path: Path) -> None:
    """在线备份数据库文件副本（sqlite3 backup API，锁安全）。"""
    conn = _require_conn()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    dest = sqlite3.connect(str(target_path))
    try:
        with _lock:
            conn.backup(dest)
    finally:
        dest.close()
