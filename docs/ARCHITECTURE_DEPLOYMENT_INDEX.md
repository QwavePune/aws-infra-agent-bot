# Architecture Deployment Docs Index

These documents cover the secondary diagram-driven workflow implemented under `/api/architecture/*`.

## Read In This Order

1. [SYSTEM_ARCHITECTURE.md](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/docs/SYSTEM_ARCHITECTURE.md)
   This explains where architecture-driven deployment sits in the broader system.

2. [ARCHITECTURE_DRIVEN_DEPLOYMENT.md](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/docs/ARCHITECTURE_DRIVEN_DEPLOYMENT.md)
   User-facing description of the parse, generate, and deploy endpoints.

3. [ARCHITECTURE_DEPLOYMENT_IMPLEMENTATION.md](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/docs/ARCHITECTURE_DEPLOYMENT_IMPLEMENTATION.md)
   Implementation notes and current limitations.

4. [QUICK_START_ARCHITECTURE_DEPLOYMENT.md](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/docs/QUICK_START_ARCHITECTURE_DEPLOYMENT.md)
   Minimal local steps and example calls.

## Scope Reminder

Architecture-driven deployment is implemented, but it is not the primary control plane of this repository. The most mature path remains the AGUI chat runtime backed by the AWS Terraform MCP server, maker-checker approval, and audit logging.
