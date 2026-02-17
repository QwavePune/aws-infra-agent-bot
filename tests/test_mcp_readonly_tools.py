"""Unit tests for MCP read-only inventory/list/describe tools."""

from unittest.mock import MagicMock

import pytest

from mcp_servers.aws_terraform_server import MCPAWSManagerServer


@pytest.fixture
def server():
    s = MCPAWSManagerServer()
    s.rbac.identity = {"Arn": "arn:aws:iam::123456789012:user/test"}
    return s


def test_readonly_tools_are_exposed(server):
    tool_names = {tool["name"] for tool in server.list_tools()}
    assert "list_account_inventory" in tool_names
    assert "list_aws_resources" in tool_names
    assert "describe_resource" in tool_names


def test_execute_tool_routes_list_aws_resources(server, monkeypatch):
    monkeypatch.setattr(
        server,
        "_list_aws_resources",
        lambda params: {"success": True, "resource_type": params["resource_type"], "count": 0, "items": []},
    )
    result = server.execute_tool("list_aws_resources", {"resource_type": "ec2", "region": "ap-south-1"})
    assert result["success"] is True
    assert result["resource_type"] == "ec2"


def test_execute_tool_routes_describe_resource(server, monkeypatch):
    monkeypatch.setattr(
        server,
        "_describe_resource",
        lambda params: {"success": True, "resource_type": params["resource_type"], "resource_id": params["resource_id"], "details": {}},
    )
    result = server.execute_tool("describe_resource", {"resource_type": "vpc", "resource_id": "vpc-123"})
    assert result["success"] is True
    assert result["resource_id"] == "vpc-123"


def test_list_account_inventory_summarizes_counts(server, monkeypatch):
    def fake_list_aws_resources(params):
        rtype = params["resource_type"]
        region = params.get("region")
        if rtype == "s3":
            return {"success": True, "count": 2, "items": []}
        per_region = {"ec2": 3, "vpc": 1, "rds": 0, "lambda": 4}
        return {"success": True, "resource_type": rtype, "region": region, "count": per_region[rtype], "items": []}

    monkeypatch.setattr(server, "_list_aws_resources", fake_list_aws_resources)

    result = server._list_account_inventory({"regions": ["ap-south-1", "us-east-1"]})
    assert result["success"] is True
    assert result["summary"]["s3"] == 2
    assert result["summary"]["ec2"] == 6
    assert result["summary"]["vpc"] == 2
    assert result["summary"]["rds"] == 0
    assert result["summary"]["lambda"] == 8
    assert len(result["regional_breakdown"]) == 2


def test_list_aws_resources_s3_with_mocked_boto(server, monkeypatch):
    fake_s3 = MagicMock()
    fake_s3.list_buckets.return_value = {
        "Buckets": [{"Name": "bucket-a", "CreationDate": "2026-01-01"}]
    }

    def fake_client(service_name, region_name=None):
        assert service_name == "s3"
        return fake_s3

    monkeypatch.setattr("mcp_servers.aws_terraform_server.boto3.client", fake_client)
    result = server._list_aws_resources({"resource_type": "s3"})
    assert result["success"] is True
    assert result["count"] == 1
    assert result["items"][0]["name"] == "bucket-a"

