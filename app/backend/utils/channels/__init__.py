"""通知渠道工具模块（邮件、PushPlus 等）。"""

from __future__ import annotations

from .email import format_email_error, send_email
from .email_templates import TEMPLATE_OPTIONS, render_email_template
from .pushplus import format_pushplus_error, send_pushplus

__all__ = [
    "send_email",
    "format_email_error",
    "send_pushplus",
    "format_pushplus_error",
    "render_email_template",
    "TEMPLATE_OPTIONS",
]
