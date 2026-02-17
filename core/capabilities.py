"""Capability query detection and response rendering."""

from typing import Any, Dict, List, Optional


CAPABILITY_PHRASES = (
    "what can you do",
    "what all can you do",
    "capabilities",
    "help me with",
    "how can you help",
)


def is_capabilities_request(message: str) -> bool:
    """Return True when the user asks for capabilities/help."""
    text = (message or "").strip().lower()
    return any(phrase in text for phrase in CAPABILITY_PHRASES)


def _format_tool_lines(tools: List[Dict[str, Any]]) -> str:
    lines = []
    for tool in tools:
        name = tool.get("name", "unknown_tool")
        desc = tool.get("description", "").strip() or "No description provided."
        lines.append(f"- `{name}`: {desc}")
    return "\n".join(lines)


def build_capabilities_response(mcp_server_name: Optional[str], mcp_server: Optional[Any]) -> str:
    """Build a context-independent capabilities summary for the active MCP server."""
    base = [
        "I can help with cloud infrastructure planning and execution workflows.",
        "For this session, here are my available capabilities:",
    ]

    if mcp_server_name == "aws_terraform" and mcp_server:
        try:
            tools = mcp_server.list_tools()
        except Exception:
            tools = []

        if tools:
            base.append("- I can use the following MCP tools:")
            base.append(_format_tool_lines(tools))
            base.append("- I can also explain tool outputs and suggest next actions.")
            return "\n".join(base)

    base.append("- No MCP tool server is currently active.")
    base.append("- I can still answer general guidance questions, but cannot execute infra actions until MCP is enabled.")
    return "\n".join(base)

