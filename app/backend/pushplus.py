"""PushPlus 工具模块门面（实现位于 app.backend.utils.channels.pushplus）。"""
import sys
try:
    from .utils.channels import pushplus as _impl
except (ImportError, ValueError):
    try:
        from utils.channels import pushplus as _impl
    except (ImportError, ValueError):
        import utils.channels.pushplus as _impl

sys.modules[__name__] = _impl
