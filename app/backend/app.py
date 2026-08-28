"""应用工厂：装配配置、扩展、中间件、错误处理、蓝图与数据库迁移。

设计要点：
- 唯一 ``create_app()`` 入口，杜绝模块级全局 app 实例与循环引用；
- 配置按环境隔离（Development / Production / Testing）；
- 数据库启动流程：旧库就地升级（bootstrap）→ Alembic 自动迁移（幂等）；
- 全局 Error Handler 统一转译 ``{code, message, data}`` 响应。
"""
from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, Response
from flask_migrate import upgrade

from . import config as app_config
from .api import register_blueprints
from .core import exceptions
from .core.middleware import (
    GatewayPrefixMiddleware,
    check_admin_only,
    ensure_default_categories,
    parse_identity,
)
from .core.response import error as error_response
from .extensions import db, migrate
from .storage import bootstrap

# Alembic 迁移脚本目录（与 app.py 同级的 migrations/）
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def create_app(
    config_object: type[app_config.BaseConfig] | None = None,
    *,
    allow_headerless_local_identity: bool | None = None,
) -> Flask:
    """创建并配置 Flask 应用。

    Parameters
    ----------
    config_object : 配置类（默认按环境自动选择，见 ``config.get_config``）。
    allow_headerless_local_identity : bool | None
        本地 TCP 开发模式允许无身份头请求（回退为 local 管理员）。
        显式传入时优先于配置类；None 时使用配置类的默认值。
    """
    config_cls = config_object or app_config.get_config()
    app = Flask(
        __name__,
        static_folder=str(app_config.www_dir()),
        static_url_path="",
    )
    app.config.from_object(config_cls)
    if allow_headerless_local_identity is not None:
        app.config["ALLOW_HEADERLESS_LOCAL"] = allow_headerless_local_identity
    # SQLALCHEMY_DATABASE_URI 依赖运行时路径（--db / 环境变量），无法在配置类里静态求值。
    # 两点必须处理：
    # 1) 绝对路径——Flask-SQLAlchemy 3.x 会把相对 sqlite 路径拼接到 app.instance_path，
    #    导致指向不存在的 instance/<相对路径> 而报 unable to open database file；
    # 2) 父目录先行创建——引擎首次连接时目录缺失同样报 unable to open database file。
    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI")
    if not db_uri:
        db_file = app_config.db_path().resolve()
        db_file.parent.mkdir(parents=True, exist_ok=True)
        db_uri = f"sqlite:///{db_file.as_posix()}"
    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri

    # 扩展单例（扩展实例在 extensions.py，随应用初始化）
    db.init_app(app)
    migrate.init_app(app, db, directory=str(MIGRATIONS_DIR))

    # WSGI 层网关前缀剥离（必须在 Flask 创建 Request 之前改写 PATH_INFO）
    app.wsgi_app = GatewayPrefixMiddleware(
        app.wsgi_app, app_config.gateway_prefix(), app_config.www_dir()
    )

    # 请求边界中间件：身份解析 → 管理员校验 → 默认分类补种
    app.before_request(parse_identity)
    app.before_request(check_admin_only)
    app.before_request(ensure_default_categories)

    _register_error_handlers(app)
    register_blueprints(app)

    # 数据库就绪：旧库就地升级 → Alembic 自动迁移 → 补种默认设置行
    # （全新库/旧库均幂等；安装向导 reminder_days 在此生效）
    with app.app_context():
        bootstrap.bootstrap_legacy_database()
        upgrade(directory=str(MIGRATIONS_DIR))
        with db.engine.begin() as conn:
            bootstrap.seed_default_settings(conn)

    return app


# --------------------------------------------------------------------------- #
# 全局异常处理
# --------------------------------------------------------------------------- #

def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(exceptions.ApiError)
    def handle_api_error(exc: exceptions.ApiError) -> Response:
        return jsonify({
            "code": exc.code,
            "message": exc.message,
            "data": exc.payload,
        }), exc.status_code

    @app.errorhandler(ValueError)
    def handle_value_error(exc: ValueError) -> Response:
        return error_response(str(exc), 400)

    @app.errorhandler(404)
    def handle_not_found(exc) -> Response:
        return error_response("接口不存在", 404)

    @app.errorhandler(413)
    def handle_payload_too_large(exc) -> Response:
        limit = app_config.MAX_REQUEST_BODY_BYTES
        return error_response(f"请求体过大，不能超过 {limit} 字节", 413)

    @app.errorhandler(500)
    def handle_internal_error(exc) -> Response:
        app.logger.exception("API 处理失败")
        return error_response("服务器内部错误", 500)
