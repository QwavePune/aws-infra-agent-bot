# Documentation Index

This documentation set is centered on the current implementation, where the browser-based AGUI runtime is the primary operational path and the AWS Terraform MCP server is the primary execution backend.

## Start Here

- [SYSTEM_ARCHITECTURE.md](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/docs/SYSTEM_ARCHITECTURE.md): full architecture, rationale, nuances, and embedded PlantUML diagrams.
- [ARCHITECTURE.md](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/docs/ARCHITECTURE.md): short-form architecture summary.
- [TERRAFORM_MCP_GUIDE.md](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/docs/TERRAFORM_MCP_GUIDE.md): AWS MCP and Terraform execution model.
- [MAKER_CHECKER_IAM.md](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/docs/MAKER_CHECKER_IAM.md): maker-checker roles and runtime behavior.

## Current System Positioning

The repo currently contains four major capabilities:

1. Chat-driven infrastructure operations through `bin/agui_server.py` and `ui/*`
2. Terraform-backed AWS execution through `mcp_servers/aws_terraform_server.py`
3. Governance workflows through maker-checker APIs and audit logs
4. Secondary architecture-driven workflows through `/api/architecture/*`

The key implementation nuance is that architecture-driven deployment is no longer the main story. The most mature path is the chat console with streamed tool execution, AWS identity awareness, approval gating, and audit visibility.

## Supporting Documents

- [CREDENTIAL_STORAGE.md](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/docs/CREDENTIAL_STORAGE.md)
- [CLI_GUIDE.md](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/docs/CLI_GUIDE.md)
- [LOGGING_GUIDE.md](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/docs/LOGGING_GUIDE.md)
- [REGRESSION_TESTING.md](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/docs/REGRESSION_TESTING.md)
- [DEVOPS_SETUP.md](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/docs/DEVOPS_SETUP.md)

## Diagrams

The live diagram sources are under [diagrams/README.md](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/diagrams/README.md).
