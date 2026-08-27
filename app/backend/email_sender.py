"""邮件工具模块门面（实现位于 app.backend.utils.channels.email）。"""
import sys
try:
    from .utils.channels import email as _impl
except (ImportError, ValueError):
    try:
        from utils.channels import email as _impl
    except (ImportError, ValueError):
        import utils.channels.email as _impl

sys.modules[__name__] = _impl
