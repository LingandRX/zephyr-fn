"""订阅模板业务服务：远程拉取、严格 Schema 校验、原子替换与回退保障。"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .. import paths, repositories
from ..domain.exceptions import ValidationError
from ..extensions import db

logger = logging.getLogger("subscription.templates")

# 限制远程模板文件体积上限：2MB
MAX_TEMPLATE_FILE_SIZE = 2 * 1024 * 1024
REQUEST_TIMEOUT = 15

VALID_PERIOD_TYPES = frozenset({"month", "quarter", "year", "once", "custom"})


def _remote_cache_path() -> Path:
    return paths.data_dir() / "subscription_templates.json"


def _builtin_templates_path() -> Path:
    # 优先读取打包/同级数据目录
    p = Path(__file__).resolve().parent.parent / "data" / "default_templates.json"
    if p.is_file():
        return p
    # 开发环境回退
    dev_path = paths.app_root() / "frontend" / "src" / "data" / "subscriptionTemplates.json"
    if dev_path.is_file():
        return dev_path
    return p


def validate_template_payload(data: Any) -> dict[str, Any]:
    """严格校验模板数据结构与类型。

    必须包含 templates 数组，且每项必须具备合法的 name、amount、period_type。
    """
    if not isinstance(data, dict):
        raise ValidationError("模板数据格式错误：根节点必须为 JSON 对象")

    templates = data.get("templates")
    if not isinstance(templates, list):
        raise ValidationError("模板数据格式错误：必须包含 templates 数组")

    if len(templates) == 0:
        raise ValidationError("模板数据无效：templates 列表不能为空")

    categories = data.get("categories")
    if categories is not None and not isinstance(categories, dict):
        raise ValidationError("模板数据格式错误：categories 必须为对象")

    cleaned_templates: list[dict[str, Any]] = []
    for idx, item in enumerate(templates):
        if not isinstance(item, dict):
            raise ValidationError(f"第 {idx + 1} 项模板格式错误：必须为对象")

        name = str(item.get("name") or "").strip()
        if not name:
            raise ValidationError(f"第 {idx + 1} 项模板缺少服务名称 (name)")

        raw_amount = item.get("amount")
        if raw_amount is None:
            raise ValidationError(f"模板「{name}」缺少金额 (amount)")
        try:
            amount = int(raw_amount)
            if amount < 0:
                raise ValueError()
        except (TypeError, ValueError) as err:
            raise ValidationError(f"模板「{name}」金额无效：必须为非负整数（单位：分）") from err

        period_type = str(item.get("period_type") or "month").strip().lower()
        if period_type not in VALID_PERIOD_TYPES:
            raise ValidationError(
                f"模板「{name}」周期无效：{period_type}，支持的值为 {', '.join(sorted(VALID_PERIOD_TYPES))}"
            )

        cleaned: dict[str, Any] = {
            "id": str(item.get("id") or f"tpl_{idx + 1}"),
            "name": name,
            "category": str(item.get("category") or "other"),
            "currency": str(item.get("currency") or "CNY"),
            "amount": amount,
            "period_type": period_type,
            "auto_renew": bool(item.get("auto_renew", True)),
        }
        if item.get("notes") is not None:
            cleaned["notes"] = str(item.get("notes"))
        if item.get("popular"):
            cleaned["popular"] = True

        cleaned_templates.append(cleaned)

    cleaned_categories: dict[str, Any] = {}
    if isinstance(categories, dict):
        for k, v in categories.items():
            if isinstance(v, dict) and "label" in v:
                cleaned_categories[str(k)] = {
                    "label": str(v["label"]),
                    "icon": str(v.get("icon") or "📦"),
                }

    return {
        "categories": cleaned_categories,
        "templates": cleaned_templates,
    }


def get_active_templates() -> dict[str, Any]:
    """获取当前生效的模板列表。

    优先返回本地远程缓存；若不存在或已损坏则降级回退至内置底包。
    """
    cache_path = _remote_cache_path()
    if cache_path.is_file():
        try:
            content = cache_path.read_text(encoding="utf-8")
            data = json.loads(content)
            validated = validate_template_payload(data)
            settings = repositories.get_app_settings()
            return {
                "source": "remote",
                "synced_at": settings.get("template_last_synced_at"),
                "data": validated,
            }
        except Exception as err:
            logger.warning("读取远程模板缓存失败，降级回退至内置模板: %s", err)

    builtin_path = _builtin_templates_path()
    if builtin_path.is_file():
        try:
            content = builtin_path.read_text(encoding="utf-8")
            data = json.loads(content)
            return {
                "source": "builtin",
                "synced_at": None,
                "data": data,
            }
        except Exception as err:
            logger.error("读取内置模板文件失败: %s", err)

    return {
        "source": "builtin",
        "synced_at": None,
        "data": {"categories": {}, "templates": []},
    }


def sync_remote_templates(url: str | None = None) -> dict[str, Any]:
    """从指定或已配置的 URL 同步远程模板。"""
    settings = repositories.get_app_settings()
    sync_url = (url or settings.get("template_sync_url") or "").strip()
    if not sync_url:
        raise ValidationError("未指定模板源地址，请先在设置中配置 URL")

    if not (sync_url.startswith("http://") or sync_url.startswith("https://")):
        raise ValidationError("模板源地址必须以 http:// 或 https:// 开头")

    logger.info("开始同步远程模板: %s", sync_url)
    req = urllib.request.Request(
        sync_url,
        headers={
            "User-Agent": "Mozilla/5.0 Zephyr-Subscription/1.0",
            "Accept": "application/json, text/plain, */*",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            # 限制读取大小以防止内存溢出
            raw_bytes = bytearray()
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                raw_bytes.extend(chunk)
                if len(raw_bytes) > MAX_TEMPLATE_FILE_SIZE:
                    raise ValidationError("远程模板文件体积过大（不得超过 2MB）")
            text = raw_bytes.decode("utf-8")
    except urllib.error.HTTPError as err:
        logger.warning("下载远程模板 HTTP 错误: %s %s", err.code, err.reason)
        raise ValidationError(f"下载远程模板失败: HTTP {err.code} {err.reason}") from err
    except urllib.error.URLError as err:
        logger.warning("下载远程模板网络错误: %s", err.reason)
        raise ValidationError(f"连接模板源超时或无法访问: {err.reason}") from err
    except UnicodeDecodeError as err:
        raise ValidationError("模板文件内容编码错误：必须为 UTF-8 编码文本") from err
    except ValidationError:
        raise
    except Exception as err:
        logger.exception("下载远程模板异常")
        raise ValidationError(f"同步失败: {err}") from err

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as err:
        raise ValidationError(f"模板文件无法解析为合法的 JSON: {err}") from err

    validated = validate_template_payload(parsed)

    # 原子安全落盘
    cache_path = _remote_cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = cache_path.with_suffix(".tmp")
    try:
        temp_path.write_text(json.dumps(validated, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(cache_path)
    except Exception as err:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise ValidationError(f"保存模板文件失败: {err}") from err

    now_iso = datetime.now(UTC).isoformat()
    with db.session.begin():
        repositories.update_app_settings({"template_last_synced_at": now_iso})

    logger.info("远程模板同步成功，共 %d 条模板", len(validated["templates"]))
    return {
        "source": "remote",
        "synced_at": now_iso,
        "count": len(validated["templates"]),
        "data": validated,
    }


def reset_templates() -> dict[str, Any]:
    """清空远程缓存文件，恢复出厂默认模板。"""
    cache_path = _remote_cache_path()
    if cache_path.is_file():
        try:
            cache_path.unlink()
            logger.info("已删除远程模板缓存文件: %s", cache_path)
        except OSError as err:
            logger.warning("删除模板缓存文件异常: %s", err)

    with db.session.begin():
        repositories.update_app_settings({"template_last_synced_at": None})

    active = get_active_templates()
    return {
        "source": "builtin",
        "synced_at": None,
        "count": len(active["data"].get("templates", [])),
    }
