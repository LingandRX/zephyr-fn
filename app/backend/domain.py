"""领域逻辑模块门面（实现位于 app.backend.core.domain）。"""
import sys
try:
    from .core import domain as _impl
except (ImportError, ValueError):
    try:
        from core import domain as _impl
    except (ImportError, ValueError):
        import core.domain as _impl

sys.modules[__name__] = _impl
