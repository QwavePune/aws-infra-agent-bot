"""Capability query detection and response rendering."""

from typing import Any, Dict, List, Optional


CAPABILITY_PHRASES = (
    "what can you do",
    "what all can you do",
    "capabilities",
    "help me with",
    "how can you help",
)

AUDIENCE_PHRASES = (
    "who is the audience for this agent",
    "who is this agent for",
    "who should use this agent",
    "who can use this agent",
    "intended audience",
    "target audience",
    "who is this for",
)


def is_capabilities_request(message: str) -> bool:
    """Return True when the user asks for capabilities/help."""
    text = (message or "").strip().lower()
    return any(phrase in text for phrase in CAPABILITY_PHRASES)


def is_audience_request(message: str) -> bool:
    """Return True when the user asks about intended audience."""
    text = (message or "").strip().lower()
    return any(phrase in text for phrase in AUDIENCE_PHRASES)


def build_audience_response() -> str:
    """Build a standard response for audience/intended-user questions."""
    return (
        "This agent is designed for technical AWS builders and operators, especially:\n"
        "- Platform, DevOps, and SRE teams\n"
        "- Cloud engineers and infrastructure developers\n"
        "- Teams that manage AWS resources using Terraform workflows\n\n"
        "It is most useful for users who want guided infrastructure planning, validation, and execution."
    )


def _dedupe_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: Dict[str, Dict[str, Any]] = {}
    for tool in tools:
        name = (tool.get("name") or "").strip()
        if not name:
            continue
        existing = deduped.get(name)
        if not existing:
            deduped[name] = tool
            continue
        if len(str(tool.get("description", ""))) > len(str(existing.get("description", ""))):
            deduped[name] = tool
    return [deduped[k] for k in sorted(deduped.keys())]


def _tool_names(tools: List[Dict[str, Any]]) -> set:
    return {t.get("name", "").strip() for t in tools if t.get("name")}


def _service_summary_sections(names: set) -> List[str]:
    sections = []
    if {"list_account_inventory", "list_aws_resources", "describe_resource"} & names:
        sections.extend([
            "- Discovery & Inventory: Account-wide listing and detailed resource lookup.",
            "  - Ask for details: `Show resource discovery capabilities`",
        ])
    if {"create_ec2_instance", "create_lambda_function", "create_ecs_service"} & names:
        sections.extend([
            "- Compute: Provision and manage EC2, Lambda, and ECS deployment flows.",
            "  - Ask for details: `Show ECS capabilities` or `Show EC2 capabilities`",
        ])
    if "create_s3_bucket" in names:
        sections.extend([
            "- Storage: S3 bucket provisioning and related setup.",
            "  - Ask for details: `Show S3 capabilities`",
        ])
    if "create_rds_instance" in names:
        sections.extend([
            "- Database: RDS provisioning workflows.",
            "  - Ask for details: `Show RDS capabilities`",
        ])
    if "create_vpc" in names:
        sections.extend([
            "- Networking: VPC/subnet infrastructure setup.",
            "  - Ask for details: `Show VPC capabilities`",
        ])
    if {"terraform_plan", "terraform_apply", "terraform_destroy", "get_infrastructure_state"} & names:
        sections.extend([
            "- Terraform Lifecycle (Generic): Plan, apply, destroy, and state operations.",
            "  - Ask for details: `Show Terraform capabilities`",
        ])
    if "get_user_permissions" in names:
        sections.extend([
            "- Identity & Access: Current AWS identity and permission context.",
            "  - Ask for details: `Show IAM capabilities`",
        ])
    if {"start_ecs_deployment_workflow", "update_ecs_deployment_workflow", "review_ecs_deployment_workflow"} & names:
        sections.extend([
            "- Guided Workflows: Multi-step orchestration with preflight validation.",
            "  - Ask for details: `Show workflow capabilities`",
        ])
    return sections


def _extract_focus(message: str) -> Optional[str]:
    text = (message or "").lower()
    focus_keywords = {
        "discovery": ("discovery", "inventory", "resource list", "describe"),
        "ecs": ("ecs", "container", "fargate"),
        "ec2": ("ec2", "instance", "compute"),
        "lambda": ("lambda",),
        "s3": ("s3", "bucket", "storage"),
        "rds": ("rds", "database", "postgres"),
        "vpc": ("vpc", "network", "subnet"),
        "terraform": ("terraform", "plan", "apply", "destroy"),
        "identity": ("iam", "identity", "permission", "access"),
        "workflow": ("workflow", "guided"),
    }
    for focus, words in focus_keywords.items():
        if any(w in text for w in words):
            return focus
    return None


def _focus_tools(tools: List[Dict[str, Any]], focus: str) -> List[Dict[str, Any]]:
    name_map = {
        "discovery": {"list_account_inventory", "list_aws_resources", "describe_resource"},
        "ecs": {"create_ecs_service", "start_ecs_deployment_workflow", "update_ecs_deployment_workflow", "review_ecs_deployment_workflow"},
        "ec2": {"create_ec2_instance"},
        "lambda": {"create_lambda_function"},
        "s3": {"create_s3_bucket"},
        "rds": {"create_rds_instance"},
        "vpc": {"create_vpc"},
        "terraform": {"terraform_plan", "terraform_apply", "terraform_destroy", "get_infrastructure_state"},
        "identity": {"get_user_permissions"},
        "workflow": {"start_ecs_deployment_workflow", "update_ecs_deployment_workflow", "review_ecs_deployment_workflow"},
    }
    allowed = name_map.get(focus, set())
    return [t for t in tools if t.get("name") in allowed]


def build_capabilities_response(mcp_server_name: Optional[str], mcp_server: Optional[Any], user_message: Optional[str] = None) -> str:
    """Build a context-independent capabilities summary for the active MCP server."""
    base = [
        "Capabilities Overview",
        "",
        "I can help with cloud infrastructure planning and execution workflows.",
        "",
        "Core Assistance:",
        "- Explain outputs from tool runs and identify next actions.",
        "- Guide multi-step infrastructure workflows with validations.",
        "",
    ]

    if mcp_server_name == "aws_terraform" and mcp_server:
        try:
            tools = mcp_server.list_tools()
        except Exception:
            tools = []

        tools = _dedupe_tools(tools)
        if tools:
            focus = _extract_focus(user_message or "")
            if focus:
                focused_tools = _focus_tools(tools, focus)
                if focused_tools:
                    base.append(f"Detailed Capabilities ({focus.upper()}):")
                    for tool in focused_tools:
                        name = tool.get("name", "unknown_tool")
                        desc = tool.get("description", "").strip() or "No description provided."
                        base.append(f"- `{name}`: {desc}")
                    return "\n".join(base)

            base.append("Available Capabilities (MCP):")
            base.extend(_service_summary_sections(_tool_names(tools)))
            base.append("")
            base.append("For detailed tool-level output, ask: `Show <service> capabilities`.")
            return "\n".join(base)

    base.append("Available Capabilities (MCP):")
    base.append("- No MCP tool server is currently active.")
    base.append("- I can still answer guidance questions, but cannot execute infra actions until MCP is enabled.")
    return "\n".join(base)
