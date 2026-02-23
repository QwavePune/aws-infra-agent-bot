"""
Azure Terraform MCP Server (dummy)

This MCP server provides a minimal Azure tool surface for AG-UI integration.
It supports:
- Listing dummy Azure resources available for build
- Returning a dummy terraform_plan response
- Returning an under-construction response for mutating operations
"""

from __future__ import annotations

from typing import Any, Dict, List


class MCPAzureManagerServer:
    """Dummy Azure MCP server for early UI and routing integration."""

    def __init__(self) -> None:
        self._resources = [
            "azurerm_resource_group",
            "azurerm_virtual_network",
            "azurerm_subnet",
            "azurerm_network_security_group",
            "azurerm_public_ip",
            "azurerm_network_interface",
            "azurerm_linux_virtual_machine",
            "azurerm_storage_account",
            "azurerm_container_registry",
            "azurerm_kubernetes_cluster",
        ]

    def initialize(self) -> Dict[str, Any]:
        return {
            "success": True,
            "message": "Azure Terraform MCP server initialized in dummy mode.",
            "user_info": {
                "tenant": "dummy-tenant",
                "subscription": "dummy-subscription",
                "mode": "under-construction",
            },
        }

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "list_azure_resources",
                "description": "List Azure Terraform resources currently available in dummy build mode.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "terraform_plan",
                "description": "Return a dummy terraform plan output for Azure projects.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "project_name": {
                            "type": "string",
                            "description": "Project name for the Terraform plan preview.",
                        }
                    },
                    "required": ["project_name"],
                },
            },
            {
                "name": "terraform_apply",
                "description": "Dummy apply endpoint. Returns under-construction response for Azure provisioning.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "project_name": {
                            "type": "string",
                            "description": "Project name intended for apply.",
                        }
                    },
                    "required": ["project_name"],
                },
            },
            {
                "name": "get_azure_subscription_context",
                "description": "Return dummy Azure subscription context.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        ]

    def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        parameters = parameters or {}

        if tool_name == "list_azure_resources":
            return {
                "success": True,
                "cloud": "azure",
                "mode": "dummy",
                "resources": self._resources,
                "message": "Azure provisioning is under construction. Resource catalog is available.",
            }

        if tool_name == "terraform_plan":
            project_name = parameters.get("project_name", "azure-demo")
            return {
                "success": True,
                "returncode": 0,
                "cloud": "azure",
                "mode": "dummy",
                "project_name": project_name,
                "stdout": (
                    "Saved the plan to: tfplan\n\n"
                    "To perform exactly these actions, run the following command to apply:\n"
                    '    terraform apply "tfplan"\n\n'
                    "Plan: 3 to add, 0 to change, 0 to destroy (dummy output)."
                ),
            }

        if tool_name == "terraform_apply":
            return {
                "success": False,
                "returncode": 1,
                "cloud": "azure",
                "mode": "dummy",
                "error": (
                    "Azure provisioning is currently under construction in this build. "
                    "terraform_apply is not available yet."
                ),
            }

        if tool_name == "get_azure_subscription_context":
            return {
                "success": True,
                "cloud": "azure",
                "mode": "dummy",
                "tenant": "dummy-tenant",
                "subscription": "dummy-subscription",
                "principal": "dummy-principal",
            }

        return {
            "success": False,
            "error": f"Unknown Azure tool: {tool_name}",
        }


mcp_server = MCPAzureManagerServer()
