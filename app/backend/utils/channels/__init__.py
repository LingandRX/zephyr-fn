"""通知渠道工具模块（邮件、PushPlus 等）。"""

from __future__ import annotations

from .email import send_email
from .email_templates import TEMPLATE_OPTIONS, render_email_template
from .pushplus import send_pushplus

__all__ = ["send_email", "send_pushplus", "render_email_template", "TEMPLATE_OPTIONS"]
