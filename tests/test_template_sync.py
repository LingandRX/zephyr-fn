"""订阅模板同步与校验单元/集成测试。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.domain.exceptions import ValidationError
from backend.services import templates as templates_service


def _json(response):
    return response.get_json(force=True)


def _assert_ok(data, code=0):
    assert data["code"] == code
    assert "data" in data


class TestTemplateValidation:
    def test_valid_payload(self):
        payload = {
            "categories": {
                "video": {"label": "视频", "icon": "🎬"}
            },
            "templates": [
                {
                    "name": "测试会员",
                    "amount": 2500,
                    "period_type": "month",
                    "currency": "CNY",
                    "auto_renew": True,
                    "notes": "备注信息",
                }
            ]
        }
        validated = templates_service.validate_template_payload(payload)
        assert len(validated["templates"]) == 1
        tpl = validated["templates"][0]
        assert tpl["name"] == "测试会员"
        assert tpl["amount"] == 2500
        assert tpl["period_type"] == "month"
        assert "video" in validated["categories"]

    def test_missing_templates_key(self):
        with pytest.raises(ValidationError, match="必须包含 templates 数组"):
            templates_service.validate_template_payload({"categories": {}})

    def test_empty_templates_list(self):
        with pytest.raises(ValidationError, match="templates 列表不能为空"):
            templates_service.validate_template_payload({"templates": []})

    def test_missing_name(self):
        payload = {
            "templates": [{"amount": 100, "period_type": "month"}]
        }
        with pytest.raises(ValidationError, match="缺少服务名称"):
            templates_service.validate_template_payload(payload)

    def test_invalid_amount(self):
        payload = {
            "templates": [{"name": "VIP", "amount": -10, "period_type": "month"}]
        }
        with pytest.raises(ValidationError, match="金额无效"):
            templates_service.validate_template_payload(payload)

    def test_invalid_period_type(self):
        payload = {
            "templates": [{"name": "VIP", "amount": 100, "period_type": "decade"}]
        }
        with pytest.raises(ValidationError, match="周期无效"):
            templates_service.validate_template_payload(payload)


class TestTemplateServiceSyncAndReset:
    def test_get_active_builtin(self, app):
        res = templates_service.get_active_templates()
        assert res["source"] in ("builtin", "remote")
        assert "data" in res
        assert "templates" in res["data"]

    def test_sync_no_url_raises(self, app):
        with pytest.raises(ValidationError, match="未指定模板源地址"):
            templates_service.sync_remote_templates(url="")

    def test_sync_invalid_url_protocol(self, app):
        with pytest.raises(ValidationError, match="必须以 http:// 或 https:// 开头"):
            templates_service.sync_remote_templates(url="ftp://example.com/templates.json")

    @patch("urllib.request.urlopen")
    def test_sync_and_reset_flow(self, mock_urlopen, app):
        mock_data = {
            "categories": {"tools": {"label": "工具", "icon": "🔧"}},
            "templates": [
                {
                    "name": "远程测试工具会员",
                    "amount": 9900,
                    "period_type": "year",
                    "currency": "CNY",
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.read.side_effect = [json.dumps(mock_data).encode("utf-8"), b""]
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = templates_service.sync_remote_templates(url="https://example.com/test_templates.json")
        assert result["source"] == "remote"
        assert result["count"] == 1
        assert result["data"]["templates"][0]["name"] == "远程测试工具会员"

        active = templates_service.get_active_templates()
        assert active["source"] == "remote"
        assert active["data"]["templates"][0]["name"] == "远程测试工具会员"

        # 测试恢复内置重置
        reset_res = templates_service.reset_templates()
        assert reset_res["source"] == "builtin"

        active_after_reset = templates_service.get_active_templates()
        assert active_after_reset["source"] == "builtin"


class TestTemplateAPI:
    def test_get_templates_api(self, client):
        resp = client.get("/api/templates")
        assert resp.status_code == 200
        body = _json(resp)
        _assert_ok(body)
        assert "data" in body
        assert "source" in body["data"]
        assert "templates" in body["data"]["data"]

    @patch("urllib.request.urlopen")
    def test_sync_templates_api(self, mock_urlopen, client):
        mock_data = {
            "templates": [
                {
                    "name": "API测试会员",
                    "amount": 5000,
                    "period_type": "month",
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.read.side_effect = [json.dumps(mock_data).encode("utf-8"), b""]
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        resp = client.post("/api/templates/sync", json={"url": "https://example.com/api.json"})
        assert resp.status_code == 200
        body = _json(resp)
        _assert_ok(body)
        assert body["data"]["source"] == "remote"
        assert body["data"]["count"] == 1

        # 验证重置端点
        resp_reset = client.post("/api/templates/reset")
        assert resp_reset.status_code == 200
        body_reset = _json(resp_reset)
        _assert_ok(body_reset)
        assert body_reset["data"]["source"] == "builtin"
