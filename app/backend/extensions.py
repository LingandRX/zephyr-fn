"""Flask 扩展单例：SQLAlchemy 与 Migrate。

独立成模块的目的：应用工厂（app.py）与模型层（models/）都引用这里的
实例，避免 ``from flask import current_app`` 或互相导入造成的循环引用。
"""

from __future__ import annotations

from contextlib import contextmanager

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()

_orig_scoped_begin = db.session.begin


@contextmanager
def _safe_session_begin(nested: bool = False):
    """统一事务边界上下文管理器。

    - 若当前会话尚未开启事务（纯写或新请求）：调用原生 begin()，在块退出时提交、异常时回滚；
    - 若当前会话已被之前的只读操作隐式开启（SQLAlchemy autobegin）：使用 savepoint 隔离，
      并在最外层 begin 块正常退出时执行统一 commit()；
    - 支持任意层级嵌套（通过 savepoint 分支隔离）。
    """
    session = db.session()
    if nested:
        with session.begin_nested():
            yield
        return

    was_in_tx = session.in_transaction()
    depth = getattr(session, "_tx_begin_depth", 0)
    session._tx_begin_depth = depth + 1
    exc_occurred = False

    try:
        if was_in_tx:
            with session.begin_nested():
                yield
        else:
            with _orig_scoped_begin():
                yield
    except BaseException:
        exc_occurred = True
        raise
    finally:
        session._tx_begin_depth -= 1
        if (
            not exc_occurred
            and session._tx_begin_depth == 0
            and was_in_tx
            and session.in_transaction()
        ):
            session.commit()


db.session.begin = _safe_session_begin
