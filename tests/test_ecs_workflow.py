"""Unit tests for guided ECS deployment workflow tools."""

import pytest

from mcp_servers.aws_terraform_server import MCPAWSManagerServer


@pytest.fixture
def server():
    s = MCPAWSManagerServer()
    s.rbac.identity = {"Arn": "arn:aws:iam::123456789012:user/test"}
    return s


def test_ecs_workflow_tools_are_exposed(server):
    names = {tool["name"] for tool in server.list_tools()}
    assert "start_ecs_deployment_workflow" in names
    assert "update_ecs_deployment_workflow" in names
    assert "review_ecs_deployment_workflow" in names
    assert "create_ecs_service" in names


def test_start_update_review_ecs_workflow(server):
    server._validate_ecs_prereqs = lambda config: {"valid": True, "errors": [], "warnings": [], "details": {}, "remediation": []}
    started = server.execute_tool(
        "start_ecs_deployment_workflow",
        {"region": "ap-south-1", "service_name": "agent-service"},
    )
    assert started["success"] is True
    assert started["ready_to_create"] is False
    workflow_id = started["workflow_id"]
    assert "cluster_name" in started["missing_fields"]

    updated = server.execute_tool(
        "update_ecs_deployment_workflow",
        {
            "workflow_id": workflow_id,
            "cluster_name": "agent-cluster",
            "container_image": "724255305552.dkr.ecr.ap-south-1.amazonaws.com/langchain-agent:latest",
            "execution_role_arn": "arn:aws:iam::123456789012:role/ecsTaskExecutionRole",
            "task_role_arn": "arn:aws:iam::123456789012:role/langchain-task-role",
            "subnet_ids": ["subnet-111", "subnet-222"],
            "security_group_ids": ["sg-111"],
        },
    )
    assert updated["success"] is True
    assert updated["ready_to_create"] is True
    assert updated["missing_fields"] == []
    assert updated["preflight"]["valid"] is True

    reviewed = server.execute_tool("review_ecs_deployment_workflow", {"workflow_id": workflow_id})
    assert reviewed["success"] is True
    assert reviewed["ready_to_create"] is True
    assert reviewed["plan"]["service_name"] == "agent-service"
    assert reviewed["preflight"]["valid"] is True


def test_create_ecs_service_from_workflow(server, monkeypatch):
    server._validate_ecs_prereqs = lambda config: {"valid": True, "errors": [], "warnings": [], "details": {}, "remediation": []}
    started = server.execute_tool(
        "start_ecs_deployment_workflow",
        {
            "region": "ap-south-1",
            "cluster_name": "agent-cluster",
            "service_name": "agent-service",
            "container_image": "public.ecr.aws/docker/library/nginx:latest",
            "execution_role_arn": "arn:aws:iam::123456789012:role/ecsTaskExecutionRole",
            "task_role_arn": "arn:aws:iam::123456789012:role/langchain-task-role",
            "subnet_ids": ["subnet-111", "subnet-222"],
            "security_group_ids": ["sg-111"],
        },
    )
    workflow_id = started["workflow_id"]

    monkeypatch.setattr(server.terraform, "init", lambda project_name: {"success": True, "project_name": project_name})

    created = server.execute_tool("create_ecs_service", {"workflow_id": workflow_id})
    assert created["success"] is True
    assert created["project_name"].startswith("ecs_agent-service_ap-south-1")
    assert created["preflight"]["valid"] is True


def test_create_ecs_service_blocks_on_preflight_errors(server):
    server._validate_ecs_prereqs = lambda config: {
        "valid": False,
        "errors": ["Invalid or missing subnet IDs: ['subnet-bad']"],
        "warnings": [],
        "details": {"region": "ap-south-1"},
        "remediation": ["use real subnet ids"],
    }

    started = server.execute_tool(
        "start_ecs_deployment_workflow",
        {
            "region": "ap-south-1",
            "cluster_name": "agent-cluster",
            "service_name": "agent-service",
            "container_image": "public.ecr.aws/docker/library/nginx:latest",
            "execution_role_arn": "arn:aws:iam::123456789012:role/ecsTaskExecutionRole",
            "task_role_arn": "arn:aws:iam::123456789012:role/langchain-task-role",
            "subnet_ids": ["subnet-bad"],
            "security_group_ids": ["sg-111"],
        },
    )
    result = server.execute_tool("create_ecs_service", {"workflow_id": started["workflow_id"]})
    assert result["success"] is False
    assert "preflight validation failed" in result["error"].lower()
    assert result["preflight"]["valid"] is False
