"""调度服务模块门面（实现位于 app.backend.services.scheduler）。"""
import sys
try:
    from .services import scheduler as _impl
except (ImportError, ValueError):
    try:
        from services import scheduler as _impl
    except (ImportError, ValueError):
        import services.scheduler as _impl

sys.modules[__name__] = _impl
