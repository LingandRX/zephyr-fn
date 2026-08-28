"""Alembic 迁移环境（Flask-Migrate 标准模板）。

运行时由 flask_migrate 注入当前应用的 SQLAlchemy URL 与元数据：
- ``flask db upgrade``（工厂启动时自动执行）
- ``flask db migrate``（开发期基于模型差异生成新迁移）
"""
from __future__ import annotations

import logging
from logging.config import fileConfig

from alembic import context
from flask import current_app

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False：避免 alembic 的日志配置把
    # 应用自身的 "subscription" 日志器禁用（server.py 的 app.log 依赖它）
    fileConfig(config.config_file_name, disable_existing_loggers=False)

logger = logging.getLogger("alembic.env")


def get_engine():
    try:
        # Flask-SQLAlchemy >= 3
        return current_app.extensions["migrate"].db.engine
    except (TypeError, AttributeError):
        return current_app.extensions["migrate"].db.get_engine()


def get_engine_url():
    try:
        return get_engine().url.render_as_string(hide_password=False)
    except AttributeError:
        return str(get_engine().url).replace("%", "%%")


def get_metadata():
    db = current_app.extensions["migrate"].db
    if hasattr(db, "metadatas"):
        return db.metadatas[None]
    return db.metadata


config.set_main_option("sqlalchemy.url", get_engine_url())
target_db = current_app.extensions["migrate"].db


def run_migrations_offline() -> None:
    """离线模式：仅凭 URL 生成 SQL，不需要数据库连接。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=get_metadata(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连接数据库执行迁移。"""

    def process_revision_directives(context_, revision, directives):
        if getattr(config.cmd_opts, "autogenerate", False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info("No changes in schema detected.")

    connectable = get_engine()
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=get_metadata(),
            process_revision_directives=process_revision_directives,
            **current_app.extensions["migrate"].configure_args,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
