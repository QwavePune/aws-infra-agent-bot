# Diagrams

This directory contains the authoritative PlantUML sources for the current implementation.

## Files

- [functional-architecture.puml](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/diagrams/functional-architecture.puml): the real runtime topology across UI, FastAPI, MCP, Terraform, logs, and AWS.
- [terraform-infra-sequence.puml](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/diagrams/terraform-infra-sequence.puml): the primary chat-to-Terraform-to-AWS mutation path.
- [maker-checker-sequence.puml](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/diagrams/maker-checker-sequence.puml): approval, comment, and execution flow for gated mutating requests.
- [login-sequence.puml](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/diagrams/login-sequence.puml): AWS CLI login and profile-based identity refresh.

## Scope Notes

- AWS diagrams describe the real implementation.
- Azure is intentionally not modeled as a production-equivalent execution path because the current Azure MCP server is a dummy implementation.
- The architecture-driven parsing endpoints are represented as a secondary flow, not the main system narrative.
