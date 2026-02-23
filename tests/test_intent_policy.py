"""Unit tests for shared intent policy guardrails."""

from core.intent_policy import detect_read_only_intent, is_mutating_tool


def test_detect_read_only_intent_true_for_listing_queries():
    assert detect_read_only_intent("Summarize resources in my AWS account")
    assert detect_read_only_intent("List EC2 instances in ap-south-1")
    assert detect_read_only_intent("Describe vpc-12345 in us-east-1")
    assert detect_read_only_intent("What is my AWS cost this month?")


def test_detect_read_only_intent_false_for_mutating_queries():
    assert not detect_read_only_intent("Create a VPC in ap-south-1")
    assert not detect_read_only_intent("Deploy my app to ECS")
    assert not detect_read_only_intent("Apply terraform changes")


def test_detect_read_only_intent_false_when_no_readonly_signal():
    assert not detect_read_only_intent("hello there")


def test_is_mutating_tool_classification():
    assert is_mutating_tool("create_vpc")
    assert is_mutating_tool("terraform_apply")
    assert is_mutating_tool("terraform_plan")
    assert is_mutating_tool("terraform_destroy")
    assert not is_mutating_tool("list_account_inventory")
    assert not is_mutating_tool("list_aws_resources")
    assert not is_mutating_tool("describe_resource")
