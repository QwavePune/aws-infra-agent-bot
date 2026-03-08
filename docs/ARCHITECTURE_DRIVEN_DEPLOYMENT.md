# Architecture-Driven Deployment

This document covers the diagram-driven workflow implemented under `/api/architecture/*`.

## Position In The Overall System

This workflow is available and usable, but it is not the primary runtime of the project.

The main production path is still:

- AGUI chat console
- LLM tool selection
- AWS Terraform MCP execution
- optional maker-checker approval

The architecture-driven endpoints are a secondary path for users who want to start from Mermaid, images, or architecture JSON instead of chat.

## What Is Implemented

`bin/agui_server.py` currently exposes:

- `POST /api/architecture/parse-mermaid`
- `POST /api/architecture/parse-image`
- `POST /api/architecture/generate-terraform`
- `POST /api/architecture/deploy`

The flow is:

1. Parse Mermaid with heuristic regex extraction, or parse an image with an LLM vision model.
2. Produce architecture JSON.
3. Generate Terraform using an LLM.
4. Optionally write `main.tf` into `terraform_workspace/<project_name>/`.
5. Optionally run `terraform init` and `terraform plan`.

`/api/architecture/deploy` stops at a planned project. It does not automatically call `terraform_apply`.

## Important Nuances

- Mermaid parsing is heuristic, not full semantic parsing.
- Image analysis requires an LLM instance with vision support.
- Terraform generation is LLM-authored, so output quality depends on the selected model.
- The deployment endpoint uses the AWS Terraform workspace and backend, but it bypasses the richer chat-time guardrails and maker-checker orchestration used in `/api/run`.

## Example Request

### Parse Mermaid

```json
{
  "mermaid": "graph LR\n  VPC[\"AWS VPC\"]\n  EC2[\"EC2 Instance\"]\n  S3[\"S3 Bucket\"]\n  VPC --> EC2\n  EC2 --> S3"
}
```

### Deploy Parsed Architecture

```json
{
  "architecture": {
    "resources": [
      {"type": "vpc", "name": "AWS VPC"},
      {"type": "ec2", "name": "EC2 Instance"},
      {"type": "s3", "name": "S3 Bucket"}
    ],
    "relationships": [
      {"from": "VPC", "to": "EC2", "type": "connection"},
      {"from": "EC2", "to": "S3", "type": "connection"}
    ]
  }
}
```

## Recommended Reading

- [SYSTEM_ARCHITECTURE.md](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/docs/SYSTEM_ARCHITECTURE.md)
- [TERRAFORM_MCP_GUIDE.md](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/docs/TERRAFORM_MCP_GUIDE.md)
