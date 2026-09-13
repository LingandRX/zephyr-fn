"""共享测试 Fixtures。

使用 TestingConfig（内存 SQLite）创建隔离的 Flask 应用，
每个测试函数在独立的 app context + 数据库事务中运行。
"""

from __future__ import annotations

import os
import sys

# 将 app/ 加入 PYTHONPATH，保证 backend 包可按包路径导入
_APP_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "app")
sys.path.insert(0, os.path.abspath(_APP_DIR))

import pytest

from backend.app import create_app
from backend.config import TestingConfig
from backend.extensions import db as _db


@pytest.fixture()
def app():
    """创建测试用 Flask 应用，每次测试使用全新的内存数据库。"""
    flask_app = create_app(TestingConfig)
    with flask_app.app_context():
        yield flask_app


@pytest.fixture()
def client(app):
    """Flask test client，自动注入管理员身份头。"""

    class _AdminClient:
        """包装 test_client，自动注入管理员身份头。"""

        def __init__(self, flask_client):
            self._client = flask_client

        def get(self, url, **kwargs):
            headers = kwargs.pop("headers", {})
            headers.setdefault("X-Trim-Userid", "test-user")
            headers.setdefault("X-Trim-Isadmin", "true")
            return self._client.get(url, headers=headers, **kwargs)

        def post(self, url, **kwargs):
            headers = kwargs.pop("headers", {})
            headers.setdefault("X-Trim-Userid", "test-user")
            headers.setdefault("X-Trim-Isadmin", "true")
            return self._client.post(url, headers=headers, **kwargs)

        def put(self, url, **kwargs):
            headers = kwargs.pop("headers", {})
            headers.setdefault("X-Trim-Userid", "test-user")
            headers.setdefault("X-Trim-Isadmin", "true")
            return self._client.put(url, headers=headers, **kwargs)

        def delete(self, url, **kwargs):
            headers = kwargs.pop("headers", {})
            headers.setdefault("X-Trim-Userid", "test-user")
            headers.setdefault("X-Trim-Isadmin", "true")
            return self._client.delete(url, headers=headers, **kwargs)

    with app.test_client() as c:
        yield _AdminClient(c)


@pytest.fixture()
def normal_client(app):
    """非管理员 test client（X-Trim-Isadmin: false）。"""

    class _NormalClient:
        def __init__(self, flask_client):
            self._client = flask_client

        def get(self, url, **kwargs):
            headers = kwargs.pop("headers", {})
            headers.setdefault("X-Trim-Userid", "normal-user")
            headers.setdefault("X-Trim-Isadmin", "false")
            return self._client.get(url, headers=headers, **kwargs)

        def post(self, url, **kwargs):
            headers = kwargs.pop("headers", {})
            headers.setdefault("X-Trim-Userid", "normal-user")
            headers.setdefault("X-Trim-Isadmin", "false")
            return self._client.post(url, headers=headers, **kwargs)

    with app.test_client() as c:
        yield _NormalClient(c)
