"""支付流水 API。"""

from __future__ import annotations

from flask import Blueprint, g, request

from ..domain.exceptions import NotFoundError, ValidationError
from ..http.response import ok
from .. import repositories

bp = Blueprint('api_payments', __name__, url_prefix='/api')


@bp.route('/payments', methods=['GET'])
def list_payments():
    """查询支付流水。

    支持三种查询模式（优先级从高到低）：
    1. subscription_id: 查询指定订阅的流水
    2. start_date + end_date: 查询日期范围内的流水
    3. 不传参: 返回用户所有流水
    """
    subscription_id = request.args.get('subscription_id') or None
    start_date = request.args.get('start_date') or None
    end_date = request.args.get('end_date') or None

    # 模式1: 按订阅 ID 查询（严格校验归属权，防止越权访问）
    if subscription_id:
        sub = repositories.get_subscription_by_id(subscription_id, g.identity.user_id)
        if sub is None:
            raise NotFoundError("订阅不存在")
        payments = repositories.get_payments_by_subscription(
            subscription_id, user_id=g.identity.user_id
        )
        return ok(payments)

    # 模式2: 按日期范围查询
    if start_date or end_date:
        if not start_date or not end_date:
            raise ValidationError("按日期范围查询时 start_date 和 end_date 都必填")
        # 简单日期格式校验
        for date_str, name in [(start_date, "start_date"), (end_date, "end_date")]:
            if len(date_str) != 10 or date_str[4] != '-' or date_str[7] != '-':
                raise ValidationError(f"{name} 格式必须为 YYYY-MM-DD")
        payments = repositories.get_payments_by_date_range(
            user_id=g.identity.user_id,
            start_date=start_date,
            end_date=end_date,
        )
        return ok(payments)

    # 模式3: 返回用户所有流水
    payments = repositories.get_all_payments(g.identity.user_id)
    return ok(payments)
