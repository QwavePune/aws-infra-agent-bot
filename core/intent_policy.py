"""Shared intent policy utilities for read-only vs mutating operations."""

from typing import Iterable


READONLY_KEYWORDS = (
    "list",
    "listing",
    "summarize",
    "summary",
    "show",
    "inventory",
    "describe",
    "what resources",
    "cost",
    "billing",
    "spend",
)

MUTATING_KEYWORDS = (
    "create",
    "provision",
    "deploy",
    "build",
    "launch",
    "spin up",
    "apply",
    "destroy",
    "delete",
    "remove",
    "terminate",
)

MUTATING_TOOLS = {"terraform_plan", "terraform_apply", "terraform_destroy"}


def detect_read_only_intent(message: str, readonly_keywords: Iterable[str] = READONLY_KEYWORDS, mutating_keywords: Iterable[str] = MUTATING_KEYWORDS) -> bool:
    """Return True if request appears read-only and does not contain mutating intent."""
    lower_msg = (message or "").lower()
    has_readonly = any(k in lower_msg for k in readonly_keywords)
    has_mutating = any(k in lower_msg for k in mutating_keywords)
    return has_readonly and not has_mutating


def is_mutating_tool(tool_name: str) -> bool:
    """Return True for tools that can mutate infrastructure state."""
    return (tool_name or "").startswith("create_") or tool_name in MUTATING_TOOLS
