"""Unit tests for capability intent detection and response rendering."""

from core.capabilities import (
    is_capabilities_request,
    build_capabilities_response,
    is_audience_request,
    build_audience_response,
    is_maker_checker_request,
    build_maker_checker_response,
    is_out_of_scope_request,
    build_out_of_scope_response,
)


class _MockMCP:
    def list_tools(self):
        return [
            {"name": "list_account_inventory", "description": "Summarize account resources."},
            {"name": "describe_resource", "description": "Describe one resource by ID/ARN."},
        ]


def test_is_capabilities_request_matches_common_phrases():
    assert is_capabilities_request("What can you do for me?")
    assert is_capabilities_request("Can you share your capabilities")
    assert is_capabilities_request("How can you help with AWS?")
    assert is_capabilities_request("Give me a list of all MCP tools that are active for this agent")
    assert not is_capabilities_request("Create a VPC in ap-south-1")


def test_is_audience_request_matches_variations():
    assert is_audience_request("Who is the audience for this agent?")
    assert is_audience_request("Who is this agent for?")
    assert is_audience_request("What is the intended audience?")
    assert is_audience_request("Who should use this agent?")
    assert not is_audience_request("Create a VPC in ap-south-1")


def test_build_audience_response_contains_core_user_groups():
    text = build_audience_response()
    assert "devops" in text.lower()
    assert "cloud engineers" in text.lower()
    assert "terraform" in text.lower()


def test_is_maker_checker_request_matches_variations():
    assert is_maker_checker_request("How does maker-checker workflow work?")
    assert is_maker_checker_request("Explain the maker checker approval flow")
    assert not is_maker_checker_request("Create an ECS service")


def test_build_maker_checker_response_contains_approval_flow():
    text = build_maker_checker_response().lower()
    assert "approval" in text
    assert "checker" in text
    assert "queued" in text


def test_build_capabilities_response_includes_active_mcp_tools():
    text = build_capabilities_response("aws_terraform", _MockMCP())
    assert "available capabilities" in text.lower()
    assert "Discovery & Inventory" in text
    assert "Show <service> capabilities" in text


def test_build_capabilities_response_focus_drilldown():
    text = build_capabilities_response("aws_terraform", _MockMCP(), "show discovery capabilities")
    assert "Detailed Capabilities" in text
    assert "list_account_inventory" in text
    assert "describe_resource" in text


def test_build_capabilities_response_without_mcp():
    text = build_capabilities_response("none", None)
    assert "No MCP tool server is currently active." in text


def test_out_of_scope_detection_blocks_general_knowledge():
    assert is_out_of_scope_request("Who is Donald Trump?")
    assert not is_out_of_scope_request("List all AWS resources in my account")


def test_build_out_of_scope_response_mentions_agent_scope():
    text = build_out_of_scope_response().lower()
    assert "aws inventory" in text
    assert "should not answer unrelated" in text
