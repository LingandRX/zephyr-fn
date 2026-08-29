"""测试公共设施：临时目录 + 应用工厂 + 会话上下文管理。

每个测试类一个独立临时数据库（config.override 注入路径），
通过应用工厂建库（旧库引导 + Alembic 迁移幂等），
服务/仓储调用统一包在 ``self.ctx()`` 应用上下文里。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

# 让 backend 包可导入（backend 的父目录 app/ 加入 sys.path）
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from backend import config  # noqa: E402
from backend.app import create_app  # noqa: E402
from backend.extensions import db  # noqa: E402


class AppTestCase(unittest.TestCase):
    """每个测试类一个临时数据库 + Flask 应用实例。"""

    app: object

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls._old_overrides = dict(getattr(config, "_OVERRIDES", {}))
        config.override("DB_PATH", str(cls.root / "test.db"))
        config.override("WWW_DIR", str(cls.root / "www"))
        cls.app = create_app(allow_headerless_local_identity=True)
        cls.app.config["TESTING"] = True

    @classmethod
    def tearDownClass(cls):
        # 释放 SQLAlchemy 连接池，避免 Windows 下临时数据库文件被占用
        with cls.app.app_context():
            db.session.remove()
            db.engine.dispose()
        current_keys = set(getattr(config, "_OVERRIDES", {}))
        old_keys = set(cls._old_overrides)
        for key in current_keys | old_keys:
            config.override(key, cls._old_overrides.get(key))
        cls.tmp.cleanup()

    def setUp(self):
        # 每个测试方法自动持有应用上下文（仓储/服务可直接调用）
        self._ctx = self.app.app_context()
        self._ctx.push()

    def tearDown(self):
        # 弹出上下文时 Flask-SQLAlchemy 自动移除该上下文的会话
        self._ctx.pop()

    @classmethod
    def ctx(cls):
        """在应用上下文中执行服务的便捷入口（with self.ctx(): ...）。"""
        return cls.app.app_context()

    def client(self):
        return self.app.test_client()
