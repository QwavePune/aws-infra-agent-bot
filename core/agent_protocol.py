"""Shared prompt/protocol helpers for CLI and AGUI agent runtimes."""

import json
from datetime import datetime
from typing import Any, Dict, List

EXECUTION_SYSTEM_PROMPT = (
    "You are an AWS Infrastructure Execution Engine. "
    "Your ONLY output should be a tool call when an action is required. "
    "DO NOT explain what you are going to do. DO NOT ask for permission. DO NOT ask for tool outputs. "
    "THE SYSTEM AUTOMATICALLY EXECUTES YOUR TOOL CALLS AND PROVIDES THE DATA. "
    "1. For any AWS request, first CALL 'get_user_permissions' to verify identity. "
    "2. For listing/discovering resources: CALL 'list_account_inventory' for a complete summary, or 'list_aws_resources' to list specific resource types. "
    "3. For details about a specific resource: CALL 'describe_resource' with the resource ID or ARN. "
    "4. CLI mode is decommissioned; always use mode='terraform' for creation tools. "
    "5. To create: CALL the creation tool (e.g., 'create_s3_bucket'). "
    "5a. For ECS deployments, prefer guided flow: start_ecs_deployment_workflow -> update_ecs_deployment_workflow -> review_ecs_deployment_workflow -> create_ecs_service. "
    "5b. IMPORTANT: After any Terraform-based create_* tool returns a project_name, you MUST immediately call terraform_plan with that exact project_name, then terraform_apply with that exact project_name in the same run. "
    "6. If in Terraform mode, follow the flow: create -> terraform_plan -> terraform_apply. "
    "7. IMPORTANT: When calling 'terraform_plan' or 'terraform_apply', you MUST use the EXACT 'project_name' returned by the creation tool. "
    "8. For read-only user intents (list, summarize, describe, inventory), NEVER call creation/deployment/destruction tools. "
    "9. For any infrastructure workflow/tool, if a tool returns missing_fields, ask explicit follow-up questions for each missing field before any create/apply step. "
    "10. Only provide a text response AFTER all relevant tools have finished."
)


def extract_tool_calls(response: Any) -> List[Dict[str, Any]]:
    """Extract tool calls from model responses across provider variants."""
    tool_calls = getattr(response, "tool_calls", []) or []
    if tool_calls:
        return tool_calls

    additional_kwargs = getattr(response, "additional_kwargs", None) or {}
    function_call = additional_kwargs.get("function_call")
    if not function_call:
        return []

    arguments = function_call.get("arguments", {})
    if isinstance(arguments, str):
        arguments = json.loads(arguments)

    return [{
        "name": function_call["name"],
        "args": arguments,
        "id": f"call_{datetime.now().strftime('%M%S')}",
    }]


def build_followup_message(tool_name: str, result: Dict[str, Any]) -> str:
    """Build deterministic follow-up prompts for incomplete infrastructure workflow results."""
    if not isinstance(result, dict):
        return ""

    missing = result.get("missing_fields")
    if not isinstance(missing, list) or not missing:
        return ""

    questions = result.get("questions")
    if not isinstance(questions, list) or not questions:
        questions = [f"Please provide value for '{field}'." for field in missing]

    lines = ["I need a few details to continue:"]
    for idx, question in enumerate(questions, start=1):
        lines.append(f"{idx}. {question}")
    lines.append("Reply with the values, and I will continue.")
    return "\n".join(lines)


def build_ecs_followup_message(tool_name: str, result: Dict[str, Any]) -> str:
    """Backward-compatible alias for callers not yet migrated."""
    return build_followup_message(tool_name, result)
