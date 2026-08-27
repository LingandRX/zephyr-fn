"""备份服务模块门面（实现位于 app.backend.services.backup）。"""
import sys
try:
    from .services import backup as _impl
except (ImportError, ValueError):
    try:
        from services import backup as _impl
    except (ImportError, ValueError):
        import services.backup as _impl

sys.modules[__name__] = _impl
