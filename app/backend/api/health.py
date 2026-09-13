"""健康检查 API。"""

from __future__ import annotations

from flask import Blueprint

from .. import config
from ..http.response import ok

bp = Blueprint('api_health', __name__, url_prefix='/api')


@bp.route('/health', methods=['GET'])
def health_check():
    """返回应用状态与版本号。"""
    return ok({'status': 'ok', 'version': config.app_version()})
