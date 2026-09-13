"""数据持久化仓储层（SQLAlchemy 实现）。

四层架构拆解：
- 查询与写入   → 子模块（subscription_repo / category_repo / ...）
- 校验与归一化 → schemas/ 与 services/（业务层）
- 旧库就地升级 → repositories/bootstrap.py

会话生命周期由 Flask-SQLAlchemy 绑定应用/请求上下文管理；
后台线程（定时任务）通过 ``with app.app_context()`` 显式持有上下文。

模块拆分后，本文件仅负责重导出所有公开符号，确保外部调用方式不变：
    from .. import repositories
    repositories.get_all_subscriptions(...)
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# 公共工具与常量（_common.py）
# --------------------------------------------------------------------------- #

from ._common import (  # noqa: F401
    SETTINGS_FIELDS,
    SUBSCRIPTION_COLUMNS,
    SUBSCRIPTION_FIELDS,
    _SECRET_MASK_EXACT,
    _SECRET_SETTING_FIELDS,
    _to_int,
    is_secret_placeholder,
    new_id,
    now_utc,
)

# --------------------------------------------------------------------------- #
# 订阅仓储（subscription_repo.py）
# --------------------------------------------------------------------------- #

from .subscription_repo import (  # noqa: F401
    delete_subscription,
    export_db_copy,
    get_all_subscriptions,
    get_all_subscriptions_raw,
    get_subscription_by_id,
    get_subscription_dedup_keys,
    get_subscriptions_paginated,
    insert_subscription,
    insert_subscription_raw,
    replace_subscription_raw,
    restore_subscription,
    renew_subscription,
    update_subscription_fields,
)

# --------------------------------------------------------------------------- #
# 分类仓储（category_repo.py）
# --------------------------------------------------------------------------- #

from .category_repo import (  # noqa: F401
    delete_category,
    get_all_categories,
    get_all_categories_raw,
    get_category_by_id,
    get_category_count,
    insert_category,
    insert_category_raw,
    update_category,
)

# --------------------------------------------------------------------------- #
# 设置仓储（settings_repo.py）
# --------------------------------------------------------------------------- #

from .settings_repo import (  # noqa: F401
    get_app_settings,
    update_app_settings,
)

# --------------------------------------------------------------------------- #
# 通知/邮件日志仓储（notification_repo.py）
# --------------------------------------------------------------------------- #

from .notification_repo import (  # noqa: F401
    claim_notification,
    complete_notification,
    has_channel_notified_today,
    log_email,
    log_notification,
)

# --------------------------------------------------------------------------- #
# 用户播种仓储（seed_repo.py）
# --------------------------------------------------------------------------- #

from .seed_repo import (  # noqa: F401
    is_user_seeded,
    mark_user_seeded,
)

# --------------------------------------------------------------------------- #
# 支付流水仓储（payment_repo.py）
# --------------------------------------------------------------------------- #

from .payment_repo import (  # noqa: F401
    create_payment_for_subscription,
    get_all_payments,
    get_payments_by_date_range,
    get_payments_by_subscription,
    insert_payment,
)

# --------------------------------------------------------------------------- #
# 便捷引用（供测试与其他模块直接使用）
# --------------------------------------------------------------------------- #

from ..extensions import db  # noqa: F401

# --------------------------------------------------------------------------- #
# 批量导入仓储（import_repo.py）
# --------------------------------------------------------------------------- #

from .import_repo import batch_import  # noqa: F401
