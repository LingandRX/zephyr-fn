"""pytest 公共 fixtures。

提供：
- app       : 测试用 Flask 应用实例（内存 SQLite，自动建表/拆表）
- client    : Flask 测试客户端
- db_session: 带事务回滚的数据库会话（每个测试自动隔离）
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# 让 backend 包可导入（backend 的父目录 app/ 加入 sys.path）
_app_dir = str(Path(__file__).resolve().parents[1] / "app")
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)

from backend.app import create_app  # noqa: E402
from backend.extensions import db as _db  # noqa: E402


@pytest.fixture(scope="session")
def app():
    """创建测试用 Flask 应用（整个测试会话共享一个实例）。"""
    application = create_app(
        config_object=type(
            "TestConfig",
            (),
            {
                "TESTING": True,
                "DEBUG": False,
                "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                "SQLALCHEMY_TRACK_MODIFICATIONS": False,
                "ALLOW_HEADERLESS_LOCAL": True,
                "SECRET_KEY": "test-secret-key",
            },
        )
    )
    with application.app_context():
        _db.create_all()
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    """Flask 测试客户端（每个测试独立）。"""
    return app.test_client()


@pytest.fixture()
def db_session(app):
    """带事务回滚的数据库会话（每个测试自动隔离，不污染其他测试）。

    用法：
        def test_something(db_session):
            db_session.add(MyModel(...))
            db_session.commit()
            # 测试结束后自动回滚
    """
    with app.app_context():
        connection = _db.engine.connect()
        transaction = connection.begin()

        options = dict(bind=connection, binds={})
        session = _db.create_scoped_session(options=options)
        _db.session = session

        yield session

        transaction.rollback()
        connection.close()
        session.remove()
