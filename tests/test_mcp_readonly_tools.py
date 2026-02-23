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
    assert "get_cost_explorer_summary" in tool_names
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


def test_execute_tool_routes_get_cost_explorer_summary(server, monkeypatch):
    monkeypatch.setattr(
        server,
        "_get_cost_explorer_summary",
        lambda params: {"success": True, "total_cost": {"amount": 12.34, "currency": "USD"}},
    )
    result = server.execute_tool("get_cost_explorer_summary", {"granularity": "MONTHLY"})
    assert result["success"] is True
    assert result["total_cost"]["amount"] == 12.34


def test_list_account_inventory_summarizes_counts(server, monkeypatch):
    def fake_list_aws_resources(params):
        rtype = params["resource_type"]
        region = params.get("region")
        if rtype == "s3":
            return {"success": True, "count": 2, "items": []}
        per_region = {"ec2": 3, "vpc": 1, "rds": 0, "lambda": 4, "ecs": 2}
        return {"success": True, "resource_type": rtype, "region": region, "count": per_region[rtype], "items": []}

    monkeypatch.setattr(server, "_list_aws_resources", fake_list_aws_resources)

    result = server._list_account_inventory({"regions": ["ap-south-1", "us-east-1"]})
    assert result["success"] is True
    assert result["summary"]["s3"] == 2
    assert result["summary"]["ec2"] == 6
    assert result["summary"]["vpc"] == 2
    assert result["summary"]["rds"] == 0
    assert result["summary"]["lambda"] == 8
    assert result["summary"]["ecs"] == 4
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


def test_cost_summary_uses_group_totals_when_total_is_empty(server, monkeypatch):
    fake_ce = MagicMock()
    fake_ce.get_cost_and_usage.return_value = {
        "ResultsByTime": [
            {
                "TimePeriod": {"Start": "2026-02-01", "End": "2026-02-24"},
                "Total": {},
                "Groups": [
                    {"Keys": ["Amazon S3"], "Metrics": {"UnblendedCost": {"Amount": "0.40", "Unit": "USD"}}},
                    {"Keys": ["Amazon ECS"], "Metrics": {"UnblendedCost": {"Amount": "0.49", "Unit": "USD"}}},
                ],
            }
        ]
    }

    def fake_client(service_name, region_name=None):
        assert service_name == "ce"
        assert region_name == "us-east-1"
        return fake_ce

    monkeypatch.setattr("mcp_servers.aws_terraform_server.boto3.client", fake_client)
    result = server._get_cost_explorer_summary(
        {"start_date": "2026-02-01", "end_date": "2026-02-24", "granularity": "MONTHLY"}
    )
    assert result["success"] is True
    assert result["total_cost"]["amount"] == 0.89
    assert result["service_count"] == 2
