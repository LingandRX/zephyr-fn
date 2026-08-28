"""Flask 扩展单例：SQLAlchemy 与 Migrate。

独立成模块的目的：应用工厂（app.py）与模型层（models/）都引用这里的
实例，避免 ``from flask import current_app`` 或互相导入造成的循环引用。
"""
from __future__ import annotations

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
