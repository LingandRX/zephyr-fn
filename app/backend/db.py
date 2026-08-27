"""数据访问模块门面（实现位于 app.backend.storage.db）。"""
import sys
try:
    from .storage import db as _impl
except (ImportError, ValueError):
    try:
        from storage import db as _impl
    except (ImportError, ValueError):
        import storage.db as _impl

sys.modules[__name__] = _impl
