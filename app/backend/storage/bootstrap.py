"""存量数据库的就地升级引导。

背景：旧版后端使用手写迁移（``db_version`` 表 + 逐版本 SQL）演进 schema，
当前基线为 v11。重构后版本演进交由 Flask-Migrate（Alembic）接管。

本模块负责在应用工厂中、Alembic ``upgrade()`` 之前执行：
1. 检测旧库（存在 ``db_version`` 表即视为旧库）；
2. 把旧库原地、幂等地补迁到 v11 基线（含自修复逻辑）；
3. 随后由 Alembic 0001 基线迁移（幂等 DDL）统一收敛 schema。

全新数据库不存在 ``db_version`` 表，直接走 Alembic，跳过本模块。
"""
from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import text

from .. import config
from ..extensions import db
from .repositories import new_id, now_utc

logger = logging.getLogger("subscription.db")

CURRENT_LEGACY_DB_VERSION = 12

# app_settings 的字段定义集中维护，迁移与 SETTINGS_FIELDS 共用这份清单，
# 避免新增设置字段后忘记补 schema。
_SETTINGS_COLUMN_DEFINITIONS = {
    "dark_mode": "TEXT NOT NULL DEFAULT 'system'",
    "default_currency": "TEXT NOT NULL DEFAULT 'CNY'",
    "exchange_rate_usd": "REAL NOT NULL DEFAULT 7.2",
    "exchange_rate_hkd": "REAL NOT NULL DEFAULT 0.92",
    "notification_days": "INTEGER NOT NULL DEFAULT 7",
    "notification_time": "TEXT DEFAULT '09:00'",
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
    "pushplus_smtp_host": "TEXT",
    "pushplus_smtp_port": "INTEGER",
    "pushplus_smtp_username": "TEXT",
    "pushplus_smtp_password": "TEXT",
    "pushplus_smtp_from_address": "TEXT",
    "last_check_date": "TEXT",
    "last_rate_update": "TEXT",
}

_VALID_TABLE_NAMES = frozenset({
    "app_settings", "notification_logs", "subscriptions", "categories",
    "db_version", "seeded_users",
})

# 默认分类模板（名称, 图标, 排序）。'local' 开发身份与真实 NAS 用户的
# 首次播种共用这份清单。
DEFAULT_CATEGORY_TEMPLATES = (
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
    # v12：PushPlus 专用 SMTP 配置字段，与邮件通知 SMTP 分离。
    (12, """
ALTER TABLE app_settings ADD COLUMN pushplus_smtp_host TEXT;
ALTER TABLE app_settings ADD COLUMN pushplus_smtp_port INTEGER;
ALTER TABLE app_settings ADD COLUMN pushplus_smtp_username TEXT;
ALTER TABLE app_settings ADD COLUMN pushplus_smtp_password TEXT;
ALTER TABLE app_settings ADD COLUMN pushplus_smtp_from_address TEXT;
"""),
]


# --------------------------------------------------------------------------- #
# 旧库检测
# --------------------------------------------------------------------------- #

def has_legacy_marker() -> bool:
    """存在 db_version 表说明是旧手写迁移库；Alembic 库只有 alembic_version。"""
    with db.engine.connect() as conn:
        row = conn.execute(text(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='table' AND name='db_version'"
        )).scalar_one()
    return row > 0


def bootstrap_legacy_database() -> bool:
    """旧库就地升级到 v11 基线（幂等）。

    Returns
    -------
    bool
        是否执行了升级（False 表示新库，无需处理）。
    """
    if not has_legacy_marker():
        return False
    with db.engine.begin() as conn:
        _run_migrations(conn)
        _ensure_settings_schema(conn)
        _ensure_notification_schema(conn)
        _ensure_category_schema(conn)
        _seed_default_categories(conn)
        seed_default_settings(conn)
        conn.execute(text(
            "INSERT INTO db_version (id, version) VALUES (1, :v) "
            "ON CONFLICT(id) DO UPDATE SET version=excluded.version"
        ), {"v": CURRENT_LEGACY_DB_VERSION})
    logger.info("存量数据库已就地升级到 v%d 基线", CURRENT_LEGACY_DB_VERSION)
    return True


# --------------------------------------------------------------------------- #
# 迁移执行
# --------------------------------------------------------------------------- #

def _get_db_version(conn: Any) -> int:
    row = conn.execute(text(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='db_version'"
    )).scalar_one()
    if row == 0:
        return 0
    result = conn.execute(text("SELECT version FROM db_version WHERE id=1")).first()
    return int(result[0]) if result else 0


def _column_exists(conn: Any, table: str, column: str) -> bool:
    if table not in _VALID_TABLE_NAMES:
        raise ValueError(f"非法表名: {table}")
    rows = conn.execute(text(f"PRAGMA table_info({table})")).all()
    return any(row._mapping["name"] == column for row in rows)


def _run_migrations(conn: Any) -> None:
    conn.execute(text(
        "CREATE TABLE IF NOT EXISTS db_version "
        "(id INTEGER PRIMARY KEY CHECK (id=1), version INTEGER NOT NULL)"
    ))
    version = _get_db_version(conn)
    if version > CURRENT_LEGACY_DB_VERSION:
        raise RuntimeError(
            f"数据库版本 {version} 高于当前后端支持的版本 {CURRENT_LEGACY_DB_VERSION}"
        )

    for target_version, sql in sorted(_MIGRATIONS):
        if version >= target_version:
            continue
        if target_version == 10:
            _dedupe_categories(conn)
        statements = [s.strip() for s in sql.split(";") if s.strip()]
        for stmt in statements:
            lower = stmt.lower()
            if lower.startswith("alter table"):
                tokens = stmt.split()
                table = tokens[2] if len(tokens) > 2 else ""
                column = tokens[5] if len(tokens) > 5 and tokens[3].lower() == "add" \
                    and tokens[4].lower() == "column" else ""
                if table and column and _column_exists(conn, table.strip(), column.strip()):
                    continue
            conn.execute(text(stmt))
        conn.execute(text(
            "INSERT INTO db_version (id, version) VALUES (1, :v) "
            "ON CONFLICT(id) DO UPDATE SET version=excluded.version"
        ), {"v": target_version})
        version = target_version


# --------------------------------------------------------------------------- #
# 自修复
# --------------------------------------------------------------------------- #

def _ensure_settings_schema(conn: Any) -> None:
    """修复版本号与实际 schema 不一致的旧数据库。"""
    for column, definition in _SETTINGS_COLUMN_DEFINITIONS.items():
        if not _column_exists(conn, "app_settings", column):
            conn.execute(text(f"ALTER TABLE app_settings ADD COLUMN {column} {definition}"))


def _ensure_notification_schema(conn: Any) -> None:
    """修复通知日志 schema，并保证旧数据库也具备幂等写入能力。"""
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS notification_logs (
            id TEXT PRIMARY KEY,
            subscription_id TEXT NOT NULL,
            notification_date TEXT NOT NULL,
            channel TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'sent',
            error_message TEXT,
            created_at TEXT NOT NULL
        )
    """))
    conn.execute(text(_NOTIFICATION_DEDUP_SQL))

    index_name = "idx_notification_logs_identity"
    expected_columns = ["subscription_id", "notification_date", "channel"]
    existing = conn.execute(text("PRAGMA index_list(notification_logs)")).all()
    for index in existing:
        if index._mapping["name"] != index_name:
            continue
        columns = [row._mapping["name"] for row in conn.execute(
            text(f'PRAGMA index_info("{index_name}")')
        ).all()]
        is_unique = bool(index._mapping["unique"])
        if not (is_unique and columns == expected_columns):
            conn.execute(text(f'DROP INDEX "{index_name}"'))
        break

    conn.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_notification_logs_identity "
        "ON notification_logs(subscription_id, notification_date, channel)"
    ))
    conn.execute(text("DROP TRIGGER IF EXISTS trg_notification_logs_reuse_failed"))


def _normalize_category_name(name: Any) -> str:
    raw = str(name or "")
    import unicodedata
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


def _dedupe_categories(conn: Any) -> None:
    """按归一化名称去重分类，保留 rowid 最小的，订阅重挂到保留分类。"""
    rows = conn.execute(
        text("SELECT id, user_id, name FROM categories ORDER BY rowid ASC")
    ).all()
    keep: dict[tuple[str, str], str] = {}
    doomed: list[tuple[str, str]] = []
    for r in rows:
        mapping = r._mapping
        key = (mapping["user_id"], _normalize_category_name(mapping["name"]).lower())
        kept = keep.get(key)
        if kept is None:
            keep[key] = mapping["id"]
        else:
            doomed.append((mapping["id"], kept))
    for cat_id, kept_id in doomed:
        conn.execute(
            text("UPDATE subscriptions SET category_id=:kept, updated_at=:now WHERE category_id=:cat"),
            {"kept": kept_id, "now": now_utc(), "cat": cat_id},
        )
        conn.execute(text("DELETE FROM categories WHERE id=:id"), {"id": cat_id})


def _ensure_category_schema(conn: Any) -> None:
    try:
        conn.execute(text("SELECT 1 FROM categories LIMIT 1"))
    except Exception:
        return
    _dedupe_categories(conn)
    conn.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_cat_user_name "
        "ON categories(user_id, name COLLATE NOCASE)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_cat_user_sort "
        "ON categories(user_id, sort_order)"
    ))


def _seed_default_categories(conn: Any) -> None:
    row = conn.execute(text("SELECT COUNT(DISTINCT user_id) FROM categories")).scalar_one()
    if row > 0:
        return
    for name, icon, sort_order in DEFAULT_CATEGORY_TEMPLATES:
        conn.execute(text(
            "INSERT OR IGNORE INTO categories "
            "(id, user_id, name, icon, sort_order) VALUES (:id,:u,:n,:i,:s)"
        ), {"id": new_id(), "u": "local", "n": name, "i": icon, "s": sort_order})
    conn.execute(text(
        "INSERT OR IGNORE INTO seeded_users (user_id, seeded_at) VALUES (:u, :t)"
    ), {"u": "local", "t": now_utc()})


def seed_default_settings(conn: Any) -> None:
    """补种全局设置单行（幂等）；全新库与旧库升级后统一调用。

    安装向导传入的 reminder_days 覆盖首次落库值；无向导值时不覆盖
    数据库中的已有设置。
    """
    now = now_utc()
    days = config.reminder_days_override()
    if days is not None:
        conn.execute(text(
            "INSERT INTO app_settings (id, notification_days, created_at, updated_at) "
            "VALUES (1, :days, :now, :now) "
            "ON CONFLICT(id) DO UPDATE SET "
            "notification_days=excluded.notification_days, "
            "updated_at=excluded.updated_at"
        ), {"days": days, "now": now})
    else:
        conn.execute(text(
            "INSERT OR IGNORE INTO app_settings (id, created_at, updated_at) VALUES (1, :now, :now)"
        ), {"now": now})


# --------------------------------------------------------------------------- #
# 正则工具（分类名校验在 services/categories 中使用同一份实现）
# --------------------------------------------------------------------------- #

_CATEGORY_ILLEGAL_RE = re.compile(r'[<>"\'&]')
