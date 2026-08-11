"""SQLite 数据访问层（移植自 zephyr-tarui 的 db 模块）。

- 单连接 + 线程锁（服务器多线程）
- 版本化迁移（db_version 表），升级时自动补迁
- 金额以「分」(amount) 整数存储；时间戳为 RFC3339 UTC 字符串
- 新增 user_id 列：按 NAS 登录用户（X-Trim-Userid）隔离订阅与分类数据
"""
from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import domain

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

CURRENT_DB_VERSION = 7

_MIGRATIONS: list[tuple[int, str]] = [
    (1, """
CREATE TABLE IF NOT EXISTS categories (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'local',
    name TEXT NOT NULL,
    icon TEXT,
    sort_order INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'local',
    name TEXT NOT NULL,
    amount INTEGER NOT NULL,
    currency TEXT NOT NULL DEFAULT 'CNY',
    actual_amount INTEGER,
    category_id TEXT,
    notes TEXT,
    period_type TEXT NOT NULL,
    custom_period_value INTEGER,
    custom_period_unit TEXT,
    auto_renew INTEGER NOT NULL DEFAULT 1,
    sharing_role TEXT,
    sharing_count INTEGER,
    start_date TEXT NOT NULL,
    first_payment_date TEXT,
    next_due_date TEXT,
    lifecycle TEXT NOT NULL DEFAULT 'active',
    renewal_policy TEXT NOT NULL DEFAULT 'auto',
    billing_status TEXT NOT NULL DEFAULT 'normal',
    grace_period_ends_at TEXT,
    sync_version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    dark_mode TEXT NOT NULL DEFAULT 'system',
    default_currency TEXT NOT NULL DEFAULT 'CNY',
    exchange_rate_usd REAL NOT NULL DEFAULT 7.2,
    exchange_rate_hkd REAL NOT NULL DEFAULT 0.92,
    notification_days INTEGER NOT NULL DEFAULT 3,
    do_not_disturb_start TEXT,
    do_not_disturb_end TEXT,
    auto_start INTEGER NOT NULL DEFAULT 0,
    tray_mode INTEGER NOT NULL DEFAULT 1,
    email_enabled INTEGER NOT NULL DEFAULT 0,
    smtp_host TEXT,
    smtp_port INTEGER,
    smtp_username TEXT,
    smtp_password TEXT,
    smtp_from_address TEXT,
    email_template TEXT NOT NULL DEFAULT 'default',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sub_user ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_sub_next ON subscriptions(next_due_date);
"""),
    (2, """
CREATE TABLE IF NOT EXISTS email_logs (
    id TEXT PRIMARY KEY,
    to_address TEXT NOT NULL,
    subject TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    sent_at TEXT,
    created_at TEXT NOT NULL
);
"""),
    (3, """
CREATE TABLE IF NOT EXISTS notification_logs (
    id TEXT PRIMARY KEY,
    subscription_id TEXT NOT NULL,
    notification_date TEXT NOT NULL,
    channel TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'sent',
    error_message TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notif_sub_date ON notification_logs(subscription_id, notification_date);
"""),
    (4, "ALTER TABLE app_settings ADD COLUMN notification_enabled INTEGER NOT NULL DEFAULT 1;"),
    (5, "ALTER TABLE app_settings ADD COLUMN pushplus_enabled INTEGER NOT NULL DEFAULT 0;"),
    (6, "ALTER TABLE app_settings ADD COLUMN pushplus_token TEXT;"),
    (7, "ALTER TABLE app_settings ADD COLUMN last_check_date TEXT;"),
]

# 订阅可更新字段（白名单）
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


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id() -> str:
    return uuid.uuid4().hex


# --------------------------------------------------------------------------- #
# 连接与迁移
# --------------------------------------------------------------------------- #

def connect(path: Path) -> None:
    global _conn
    path.parent.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(str(path), check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    with _lock:
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
        _run_migrations()
        _seed_default_settings()
        _conn.commit()


def _get_db_version() -> int:
    conn = _require_conn()
    row = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='db_version'"
    ).fetchone()
    if row[0] == 0:
        return 0
    row = conn.execute("SELECT version FROM db_version WHERE id=1").fetchone()
    return row[0] if row else 0


def _column_exists(table: str, column: str) -> bool:
    conn = _require_conn()
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def _run_migrations() -> None:
    conn = _require_conn()
    version = _get_db_version()
    for target_version, sql in sorted(_MIGRATIONS):
        if version < target_version:
            # ALTER TABLE ADD COLUMN 逐条执行，列已存在则跳过（幂等）
            statements = [s.strip() for s in sql.split(";") if s.strip()]
            for stmt in statements:
                lower = stmt.lower()
                if lower.startswith("alter table"):
                    table, _, rest = stmt[12:].partition(" ")
                    column = rest.split(" ")[0] if rest else ""
                    if _column_exists(table.strip(), column.strip()):
                        continue
                conn.execute(stmt)
            conn.execute(
                "CREATE TABLE IF NOT EXISTS db_version "
                "(id INTEGER PRIMARY KEY CHECK (id=1), version INTEGER NOT NULL)"
            )
            conn.execute(
                "INSERT OR REPLACE INTO db_version (id, version) VALUES (1, ?)",
                (target_version,),
            )
    # 记录最终版本
    conn.execute(
        "CREATE TABLE IF NOT EXISTS db_version "
        "(id INTEGER PRIMARY KEY CHECK (id=1), version INTEGER NOT NULL)"
    )
    conn.execute(
        "INSERT OR REPLACE INTO db_version (id, version) VALUES (1, ?)",
        (CURRENT_DB_VERSION,),
    )


def _seed_default_settings() -> None:
    conn = _require_conn()
    now = now_utc()
    conn.execute(
        "INSERT OR IGNORE INTO app_settings "
        "(id, created_at, updated_at) VALUES (1, ?, ?)",
        (now, now),
    )


def _require_conn() -> sqlite3.Connection:
    if _conn is None:
        raise RuntimeError("database not initialized")
    return _conn


# --------------------------------------------------------------------------- #
# 工具
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
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


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


def _normalize_new_subscription(user_id: str, data: dict) -> dict:
    """校验并规整创建入参（移植 create_subscription 逻辑）。"""
    name = str(data.get("name") or "").strip()
    if not name:
        raise ValueError("名称不能为空")
    period_type = str(data.get("period_type") or "month").strip()
    if period_type not in domain.PERIOD_TYPES:
        raise ValueError(f"未知周期类型: {period_type}")
    currency = str(data.get("currency") or "CNY").strip().upper()
    if currency not in ("CNY", "USD", "HKD"):
        raise ValueError(f"不支持的货币: {currency}")
    amount = _to_int(data.get("amount"), 0)
    if amount < 0:
        raise ValueError("金额不能为负数")
    actual_amount = data.get("actual_amount")
    actual_amount = _to_int(actual_amount) if actual_amount not in (None, "") else None
    start_date = _date_value(data.get("start_date")) or date.today().isoformat()
    first_payment_date = _date_value(data.get("first_payment_date"))
    next_due_date = _date_value(data.get("next_due_date"))

    custom_value = data.get("custom_period_value")
    custom_value = max(1, _to_int(custom_value, 1)) if custom_value not in (None, "") else None
    custom_unit = data.get("custom_period_unit") or "month"

    if next_due_date is None and period_type != "once":
        derived = domain.add_one_period(
            date.fromisoformat(start_date), period_type, custom_value, custom_unit
        )
        if derived:
            next_due_date = derived.isoformat()

    auto_renew = _to_bool(data.get("auto_renew", True))
    auto_renew, renewal_policy = (
        (False, "manual") if period_type == "once"
        else domain.normalize_renewal_on_create(auto_renew, data.get("renewal_policy"))
    )

    return {
        "id": new_id(),
        "user_id": user_id,
        "name": name,
        "amount": amount,
        "currency": currency,
        "actual_amount": actual_amount,
        "category_id": data.get("category_id") or None,
        "notes": (data.get("notes") or "").strip() or None,
        "period_type": period_type,
        "custom_period_value": custom_value,
        "custom_period_unit": custom_unit if period_type == "custom" else None,
        "auto_renew": int(auto_renew),
        "sharing_role": data.get("sharing_role") or None,
        "sharing_count": data.get("sharing_count"),
        "start_date": start_date,
        "first_payment_date": first_payment_date,
        "next_due_date": next_due_date,
        "lifecycle": "active",
        "renewal_policy": renewal_policy,
        "billing_status": "normal",
        "grace_period_ends_at": None,
        "sync_version": 1,
        "created_at": now_utc(),
        "updated_at": now_utc(),
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
        conn.commit()
    return get_subscription_by_id(sub["id"], user_id)


def update_subscription(sub_id: str, user_id: str, data: dict) -> dict | None:
    conn = _require_conn()
    current = get_subscription_by_id(sub_id, user_id)
    if current is None:
        return None

    updates: dict = {}
    for field in SUBSCRIPTION_FIELDS:
        if field not in data:
            continue
        value = data[field]
        if field in ("amount",):
            updates[field] = max(0, _to_int(value, 0))
        elif field in ("custom_period_value",):
            updates[field] = max(1, _to_int(value, 1)) if value not in (None, "") else None
        elif field in ("custom_period_unit", "period_type", "currency"):
            if value in (None, ""):
                continue
            updates[field] = str(value)
        elif field in ("auto_renew",):
            updates[field] = int(_to_bool(value))
        elif field in ("actual_amount",):
            updates[field] = _to_int(value) if value not in (None, "") else None
        elif field in ("start_date", "first_payment_date", "next_due_date",
                       "grace_period_ends_at"):
            updates[field] = _date_value(value)
        else:
            updates[field] = value

    # 续费策略归一化
    if "auto_renew" in updates or "renewal_policy" in data:
        auto_renew, policy = domain.resolve_renewal_on_update(
            current["auto_renew"], current["renewal_policy"],
            updates.get("auto_renew", None) if "auto_renew" in updates else None,
            data.get("renewal_policy"),
        )
        updates["auto_renew"] = int(auto_renew)
        updates["renewal_policy"] = policy

    if "renewal_policy" in updates and "auto_renew" not in updates and "auto_renew" not in data:
        updates["auto_renew"] = int(updates["renewal_policy"] == "auto")

    if not updates:
        return current

    updates["updated_at"] = now_utc()
    sets = ",".join(f"{c}=?" for c in updates)
    with _lock:
        conn.execute(
            f"UPDATE subscriptions SET {sets} WHERE id=? AND user_id=?",
            [updates[c] for c in updates] + [sub_id, user_id],
        )
        conn.commit()
    return get_subscription_by_id(sub_id, user_id)


def delete_subscription(sub_id: str, user_id: str) -> bool:
    conn = _require_conn()
    with _lock:
        cur = conn.execute(
            "DELETE FROM subscriptions WHERE id=? AND user_id=?", (sub_id, user_id)
        )
        conn.commit()
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
        conn.commit()
    return get_subscription_by_id(sub_id, user_id)


# --------------------------------------------------------------------------- #
# 分类 CRUD
# --------------------------------------------------------------------------- #

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
    name = str(data.get("name") or "").strip()
    if not name:
        raise ValueError("分类名称不能为空")
    cat_id = new_id()
    with _lock:
        conn.execute(
            "INSERT INTO categories (id, user_id, name, icon, sort_order) VALUES (?,?,?,?,?)",
            (cat_id, user_id, name, data.get("icon"), _to_int(data.get("sort_order"), 0)),
        )
        conn.commit()
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
            name = str(data.get("name") or "").strip()
            if not name:
                raise ValueError("分类名称不能为空")
            updates["name"] = name
        if "icon" in data:
            updates["icon"] = data.get("icon")
        if "sort_order" in data:
            updates["sort_order"] = _to_int(data.get("sort_order"), 0)
        if updates:
            sets = ",".join(f"{c}=?" for c in updates)
            conn.execute(
                f"UPDATE categories SET {sets} WHERE id=? AND user_id=?",
                [updates[c] for c in updates] + [cat_id, user_id],
            )
            conn.commit()
        row = conn.execute("SELECT * FROM categories WHERE id=?", (cat_id,)).fetchone()
    return dict(row)


def delete_category(cat_id: str, user_id: str) -> bool:
    conn = _require_conn()
    with _lock:
        cur = conn.execute(
            "DELETE FROM categories WHERE id=? AND user_id=?", (cat_id, user_id)
        )
        conn.commit()
    return cur.rowcount > 0


# --------------------------------------------------------------------------- #
# 设置
# --------------------------------------------------------------------------- #

def get_app_settings() -> dict:
    conn = _require_conn()
    with _lock:
        row = conn.execute("SELECT * FROM app_settings WHERE id=1").fetchone()
    return _row_to_settings(row)


def update_app_settings(data: dict) -> dict:
    conn = _require_conn()
    updates: dict = {}
    for field in SETTINGS_FIELDS:
        if field not in data:
            continue
        value = data[field]
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
        conn.commit()
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
    conn = _require_conn()
    with _lock:
        conn.execute(
            "INSERT INTO notification_logs (id, subscription_id, notification_date, "
            "channel, status, error_message, created_at) VALUES (?,?,?,?,?,?,?)",
            (new_id(), subscription_id, date.today().isoformat(),
             channel, status, error_message, now_utc()),
        )
        conn.commit()


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
        conn.commit()


# --------------------------------------------------------------------------- #
# 备份辅助（全量读取，供导出/合并使用）
# --------------------------------------------------------------------------- #

def get_all_subscriptions_raw() -> list[dict]:
    conn = _require_conn()
    with _lock:
        rows = conn.execute("SELECT * FROM subscriptions ORDER BY id").fetchall()
    return [_row_to_sub(r) for r in rows]


def get_all_categories_raw() -> list[dict]:
    conn = _require_conn()
    with _lock:
        rows = conn.execute("SELECT * FROM categories ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def get_subscription_dedup_keys(user_id: str | None = None) -> set:
    """去重键：名称|金额|周期类型（与参考项目一致）。"""
    conn = _require_conn()
    if user_id:
        rows = conn.execute(
            "SELECT name, amount, period_type FROM subscriptions WHERE user_id=?",
            (user_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT name, amount, period_type FROM subscriptions"
        ).fetchall()
    return {f"{r['name']}|{r['amount']}|{r['period_type']}".lower() for r in rows}


def insert_subscription_raw(sub: dict) -> None:
    conn = _require_conn()
    cols = list(sub.keys())
    with _lock:
        conn.execute(
            f"INSERT OR REPLACE INTO subscriptions ({','.join(cols)}) "
            f"VALUES ({','.join('?' * len(cols))})",
            [sub[c] for c in cols],
        )
        conn.commit()


def insert_category_raw(cat: dict) -> None:
    conn = _require_conn()
    with _lock:
        conn.execute(
            "INSERT OR IGNORE INTO categories (id, user_id, name, icon, sort_order) "
            "VALUES (?,?,?,?,?)",
            (cat["id"], cat.get("user_id", "local"), cat["name"],
             cat.get("icon"), cat.get("sort_order", 0)),
        )
        conn.commit()


def replace_subscription_raw(sub: dict) -> None:
    insert_subscription_raw(sub)


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
