# Implementation Checklist

This checklist reflects the current codebase status rather than the original architecture-deployment rollout plan.

## Primary Runtime

- [x] `bin/agui_server.py` is the main operational runtime
- [x] `/api/run` streams responses over SSE
- [x] browser UI supports model selection, MCP selection, identity, audit, and approvals
- [x] client-scoped AWS profile context is implemented
- [x] conversation history is stored in memory per thread

## AWS MCP And Terraform

- [x] AWS MCP server is implemented in [aws_terraform_server.py](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/mcp_servers/aws_terraform_server.py)
- [x] mutating AWS workflows are Terraform-only
- [x] Terraform projects are written under `terraform_workspace/`
- [x] `terraform_plan`, `terraform_apply`, and `terraform_destroy` are implemented
- [x] read-only inventory, resource description, and cost summary tools are implemented
- [x] guided ECS workflow and prerequisite validation are implemented

## Governance And Audit

- [x] read-only intent guardrails are enforced in the backend
- [x] maker-checker gating is implemented in AGUI
- [x] checker/maker role configuration is persisted to `logs/maker_checker_roles.json`
- [x] workflow execution is logged to JSONL with daily rotation
- [x] audit view and CSV export are implemented

## Architecture-Driven Workflow

- [x] `core/architecture_parser.py` exists
- [x] Mermaid parsing endpoint is implemented
- [x] image parsing endpoint is implemented
- [x] Terraform generation endpoint is implemented
- [x] generate-and-plan deployment endpoint is implemented
- [ ] architecture-specific MCP tools are not implemented in the AWS MCP server
- [ ] architecture-driven endpoints do not use the same rich maker-checker orchestration as `/api/run`

## Cloud Coverage

- [x] AWS backend is real
- [x] Azure backend exists as a dummy MCP implementation for UI/routing continuity
- [ ] Azure provisioning is not production-ready in this repository

## Important Constraints

- [x] Terraform state is local by default unless generated code adds a backend
- [x] Mermaid parsing is heuristic
- [x] Lambda runtime exists but is less complete than AGUI
- [x] audit storage is file-backed rather than database-backed
- [x] queue state for maker-checker requests is in-memory

## Document References

- [SYSTEM_ARCHITECTURE.md](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/docs/SYSTEM_ARCHITECTURE.md)
- [TERRAFORM_MCP_GUIDE.md](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/docs/TERRAFORM_MCP_GUIDE.md)
- [MAKER_CHECKER_IAM.md](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/docs/MAKER_CHECKER_IAM.md)
- [ARCHITECTURE_DRIVEN_DEPLOYMENT.md](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/docs/ARCHITECTURE_DRIVEN_DEPLOYMENT.md)
