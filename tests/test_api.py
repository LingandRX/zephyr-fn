"""API 集成测试（使用 Flask test_client）。

覆盖：健康检查、订阅 CRUD + 分页、分类 CRUD、设置密钥脱敏、
权限控制、支付流水。
"""

from __future__ import annotations

import json

import pytest


def _json(response):
    """解析 JSON 响应体。"""
    return response.get_json(force=True)


def _assert_ok(data, code=0):
    """断言统一响应信封结构。"""
    assert data["code"] == code
    assert "message" in data
    assert "data" in data


def _create_subscription(client, **overrides):
    """辅助：创建一个订阅并返回解析后的 JSON data。"""
    from datetime import date, timedelta
    _future = (date.today() + timedelta(days=30)).isoformat()
    payload = {
        "name": "测试订阅",
        "amount": 1900,
        "currency": "CNY",
        "period_type": "month",
        "auto_renew": True,
        "start_date": _future,
        "first_payment_date": _future,
    }
    payload.update(overrides)
    resp = client.post("/api/subscriptions", json=payload)
    assert resp.status_code == 201
    body = _json(resp)
    _assert_ok(body)
    return body["data"]


# --------------------------------------------------------------------------- #
# 健康检查
# --------------------------------------------------------------------------- #


class TestHealthAPI:
    def test_health_check(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = _json(resp)
        _assert_ok(body)
        assert body["data"]["status"] == "ok"
        assert "version" in body["data"]


# --------------------------------------------------------------------------- #
# 订阅 CRUD
# --------------------------------------------------------------------------- #


class TestSubscriptionAPI:
    def test_create_subscription(self, client):
        sub = _create_subscription(client)
        assert sub["name"] == "测试订阅"
        assert sub["amount"] == 1900
        assert sub["currency"] == "CNY"
        assert sub["status"] in ("active", "expiring", "expired")

    def test_list_subscriptions(self, client):
        _create_subscription(client, name="Sub1")
        _create_subscription(client, name="Sub2")
        resp = client.get("/api/subscriptions")
        assert resp.status_code == 200
        body = _json(resp)
        _assert_ok(body)
        assert len(body["data"]) >= 2

    def test_get_subscription(self, client):
        created = _create_subscription(client)
        sub_id = created["id"]
        resp = client.get(f"/api/subscriptions/{sub_id}")
        assert resp.status_code == 200
        body = _json(resp)
        _assert_ok(body)
        assert body["data"]["id"] == sub_id

    def test_update_subscription(self, client):
        created = _create_subscription(client)
        sub_id = created["id"]
        resp = client.put(f"/api/subscriptions/{sub_id}", json={
            "name": "更新后名称",
            "amount": 2990,
        })
        assert resp.status_code == 200
        body = _json(resp)
        _assert_ok(body)
        assert body["data"]["name"] == "更新后名称"
        assert body["data"]["amount"] == 2990

    def test_delete_subscription(self, client):
        created = _create_subscription(client)
        sub_id = created["id"]
        resp = client.delete(f"/api/subscriptions/{sub_id}")
        assert resp.status_code == 200
        body = _json(resp)
        _assert_ok(body)
        assert body["data"]["ok"] is True

        # 删除后 GET 应 404
        resp2 = client.get(f"/api/subscriptions/{sub_id}")
        assert resp2.status_code == 404

    def test_get_nonexistent_subscription(self, client):
        resp = client.get("/api/subscriptions/nonexistent-id")
        assert resp.status_code == 404

    def test_restore_subscription(self, client):
        created = _create_subscription(client)
        sub_id = created["id"]
        # 删除
        client.delete(f"/api/subscriptions/{sub_id}")
        # 恢复
        resp = client.post(f"/api/subscriptions/{sub_id}/restore")
        assert resp.status_code == 200
        body = _json(resp)
        _assert_ok(body)
        assert body["data"]["id"] == sub_id

    def test_renew_subscription(self, client):
        created = _create_subscription(client, period_type="month", start_date="2026-01-15")
        sub_id = created["id"]
        resp = client.post(f"/api/subscriptions/{sub_id}/renew")
        assert resp.status_code == 200
        body = _json(resp)
        _assert_ok(body)

    def test_renew_once_subscription_fails(self, client):
        """一次性订阅不可续费。"""
        created = _create_subscription(client, period_type="once", auto_renew=False)
        sub_id = created["id"]
        resp = client.post(f"/api/subscriptions/{sub_id}/renew")
        assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# 订阅分页
# --------------------------------------------------------------------------- #


class TestSubscriptionPagination:
    def test_pagination_basic(self, client):
        _create_subscription(client, name="Page Sub 1")
        _create_subscription(client, name="Page Sub 2")
        _create_subscription(client, name="Page Sub 3")
        resp = client.get("/api/subscriptions?page=1&per_page=2")
        assert resp.status_code == 200
        body = _json(resp)
        _assert_ok(body)
        data = body["data"]
        assert "items" in data
        assert "total" in data
        assert data["page"] == 1
        assert data["per_page"] == 2
        assert data["pages"] >= 2
        assert len(data["items"]) == 2

    def test_pagination_page_2(self, client):
        _create_subscription(client, name="Page2 Sub 1")
        _create_subscription(client, name="Page2 Sub 2")
        _create_subscription(client, name="Page2 Sub 3")
        resp = client.get("/api/subscriptions?page=2&per_page=2")
        assert resp.status_code == 200
        body = _json(resp)
        assert len(body["data"]["items"]) == 1

    def test_pagination_by_lifecycle(self, client):
        _create_subscription(client, name="Active Sub", lifecycle="active")
        resp = client.get("/api/subscriptions?page=1&per_page=10&lifecycle=active")
        assert resp.status_code == 200
        body = _json(resp)
        assert body["data"]["total"] >= 1


# --------------------------------------------------------------------------- #
# 分类 CRUD
# --------------------------------------------------------------------------- #


class TestCategoryAPI:
    def test_list_categories(self, client):
        # 先创建一个分类（确保至少有一个）
        client.post("/api/categories", json={"name": "自建分类", "icon": "📦"})
        resp = client.get("/api/categories")
        assert resp.status_code == 200
        body = _json(resp)
        _assert_ok(body)
        assert len(body["data"]) >= 1

    def test_create_category(self, client):
        resp = client.post("/api/categories", json={"name": "新分类", "icon": "📦"})
        assert resp.status_code == 201
        body = _json(resp)
        _assert_ok(body)
        assert body["data"]["name"] == "新分类"

    def test_update_category(self, client):
        resp = client.post("/api/categories", json={"name": "待更新"})
        cat_id = _json(resp)["data"]["id"]
        resp2 = client.put(f"/api/categories/{cat_id}", json={"name": "已更新"})
        assert resp2.status_code == 200
        assert _json(resp2)["data"]["name"] == "已更新"

    def test_delete_category(self, client):
        resp = client.post("/api/categories", json={"name": "待删除"})
        cat_id = _json(resp)["data"]["id"]
        resp2 = client.delete(f"/api/categories/{cat_id}")
        assert resp2.status_code == 200

    def test_create_duplicate_category_raises(self, client):
        client.post("/api/categories", json={"name": "重复分类"})
        resp2 = client.post("/api/categories", json={"name": "重复分类"})
        assert resp2.status_code == 409  # ConflictError


# --------------------------------------------------------------------------- #
# 设置
# --------------------------------------------------------------------------- #


class TestSettingsAPI:
    def test_get_settings_masks_secrets(self, client):
        """GET /api/settings 不应返回密钥原文。"""
        resp = client.get("/api/settings")
        assert resp.status_code == 200
        body = _json(resp)
        _assert_ok(body)
        data = body["data"]
        # 不应出现原始密钥字段
        assert "smtp_password" not in data
        assert "pushplus_token" not in data
        # 应有脱敏字段
        assert "smtp_password_configured" in data
        assert "smtp_password_masked" in data

    def test_update_settings(self, client):
        resp = client.put("/api/settings", json={
            "notification_days": 14,
            "default_currency": "USD",
        })
        assert resp.status_code == 200
        body = _json(resp)
        _assert_ok(body)
        # 验证更新生效
        resp2 = client.get("/api/settings")
        data2 = _json(resp2)["data"]
        assert data2["notification_days"] == 14
        assert data2["default_currency"] == "USD"


# --------------------------------------------------------------------------- #
# 权限控制
# --------------------------------------------------------------------------- #


class TestPermissions:
    def test_normal_user_cannot_access_settings(self, normal_client):
        """非管理员请求 /api/settings 应返回 403。"""
        resp = normal_client.get("/api/settings")
        assert resp.status_code == 403
        body = _json(resp)
        assert body["code"] == 403

    def test_normal_user_can_list_subscriptions(self, normal_client):
        """普通用户可以查看自己的订阅列表。"""
        resp = normal_client.get("/api/subscriptions")
        assert resp.status_code == 200

    def test_normal_user_cannot_import_csv(self, normal_client):
        """非管理员不能导入 CSV。"""
        resp = normal_client.post("/api/backup/import-csv",
                                  data="名称,金额\nTest,100",
                                  content_type="text/csv")
        assert resp.status_code == 403


# --------------------------------------------------------------------------- #
# 支付流水
# --------------------------------------------------------------------------- #


class TestPaymentsAPI:
    def test_list_payments_empty(self, client):
        """无订阅时返回空列表。"""
        resp = client.get("/api/payments")
        assert resp.status_code == 200
        body = _json(resp)
        _assert_ok(body)
        assert isinstance(body["data"], list)

    def test_payment_created_on_subscription(self, client):
        """创建订阅自动生成首笔支付流水。"""
        _create_subscription(client, name="付费订阅")
        resp = client.get("/api/payments")
        body = _json(resp)
        assert len(body["data"]) >= 1
        assert body["data"][0]["payment_type"] == "first"

    def test_payment_by_subscription_id(self, client):
        created = _create_subscription(client)
        sub_id = created["id"]
        resp = client.get(f"/api/payments?subscription_id={sub_id}")
        assert resp.status_code == 200
        body = _json(resp)
        assert len(body["data"]) >= 1
        assert body["data"][0]["subscription_id"] == sub_id

    def test_payment_by_date_range(self, client):
        _create_subscription(client)
        resp = client.get("/api/payments?start_date=2025-01-01&end_date=2027-12-31")
        assert resp.status_code == 200
        body = _json(resp)
        assert len(body["data"]) >= 1

    def test_payment_date_range_requires_both(self, client):
        """start_date 和 end_date 必须同时提供。"""
        resp = client.get("/api/payments?start_date=2025-01-01")
        assert resp.status_code == 400

    def test_user_cannot_access_other_users_payments(self, client, normal_client):
        """用户不能通过 subscription_id 越权查看其他用户的支付流水。"""
        created = _create_subscription(client, name="管理员私密订阅")
        sub_id = created["id"]
        # normal_client 用户与 client 用户 ID 不同（test-user vs normal-user）
        resp = normal_client.get(f"/api/payments?subscription_id={sub_id}")
        assert resp.status_code == 404
        body = _json(resp)
        assert body["code"] == 404


# --------------------------------------------------------------------------- #
# 错误处理
# --------------------------------------------------------------------------- #


class TestErrorHandling:
    def test_404_not_found(self, client):
        resp = client.get("/api/nonexistent-endpoint")
        assert resp.status_code == 404

    def test_create_with_invalid_json(self, client):
        """传入非 JSON 应触发 400 或统一错误。"""
        resp = client.post(
            "/api/subscriptions",
            data="not json",
            content_type="application/json",
        )
        assert resp.status_code in (400, 415, 500)  # Flask/Werkzeug 行为差异
