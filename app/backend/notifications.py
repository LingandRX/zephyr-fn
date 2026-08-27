"""通知服务模块门面（实现位于 app.backend.services.notifications）。"""
import sys
try:
    from .services import notifications as _impl
except (ImportError, ValueError):
    try:
        from services import notifications as _impl
    except (ImportError, ValueError):
        import services.notifications as _impl

sys.modules[__name__] = _impl
