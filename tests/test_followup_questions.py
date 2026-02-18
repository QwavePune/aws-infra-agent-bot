"""Unit tests for generic missing-field follow-up questions."""

import pytest

from mcp_servers.aws_terraform_server import MCPAWSManagerServer


@pytest.fixture
def server():
    s = MCPAWSManagerServer()
    s.rbac.identity = {"Arn": "arn:aws:iam::123456789012:user/test"}
    return s


def test_create_s3_bucket_returns_missing_questions(server):
    result = server.execute_tool("create_s3_bucket", {})
    assert result["success"] is False
    assert set(result["missing_fields"]) == {"bucket_name", "region"}
    assert len(result["questions"]) >= 2


def test_create_ec2_instance_requires_region(server):
    result = server.execute_tool("create_ec2_instance", {})
    assert result["success"] is False
    assert result["missing_fields"] == ["region"]
    assert len(result["questions"]) == 1


def test_start_ecs_workflow_includes_region_question(server):
    result = server.execute_tool("start_ecs_deployment_workflow", {"service_name": "agent-service"})
    assert result["success"] is True
    assert "region" in result["missing_fields"]
    assert any("region" in q.lower() for q in result["questions"])
