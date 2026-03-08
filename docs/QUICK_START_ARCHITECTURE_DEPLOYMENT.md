# Quick Start: Architecture-Driven Deployment

This quick start is for the secondary architecture endpoints, not the main chat console workflow.

## Start The Server

```bash
python bin/agui_server.py
```

Server default: `http://localhost:9595`

## Parse Mermaid

```bash
curl -X POST http://localhost:9595/api/architecture/parse-mermaid \
  -H "Content-Type: application/json" \
  -d '{
    "mermaid": "graph LR\n  VPC[\"VPC\"]\n  EC2[\"EC2\"]\n  S3[\"S3\"]\n  VPC --> EC2\n  EC2 --> S3"
  }'
```

## Generate Terraform

```bash
curl -X POST http://localhost:9595/api/architecture/generate-terraform \
  -H "Content-Type: application/json" \
  -d '{
    "architecture": {
      "resources": [
        {"type": "vpc", "name": "VPC"},
        {"type": "ec2", "name": "EC2"},
        {"type": "s3", "name": "S3"}
      ],
      "relationships": [
        {"from": "VPC", "to": "EC2", "type": "connection"},
        {"from": "EC2", "to": "S3", "type": "connection"}
      ]
    }
  }'
```

## Generate And Plan

```bash
curl -X POST http://localhost:9595/api/architecture/deploy \
  -H "Content-Type: application/json" \
  -d '{
    "architecture": {
      "resources": [
        {"type": "ec2", "name": "web-server"},
        {"type": "s3", "name": "data-bucket"}
      ],
      "relationships": [
        {"from": "web-server", "to": "data-bucket", "type": "connection"}
      ]
    }
  }'
```

## Important Caveats

- `/api/architecture/deploy` generates and plans; it does not automatically apply.
- Mermaid parsing is heuristic.
- Image parsing requires a vision-capable LLM provider.
- The main operational controls still live in the chat runtime under `/api/run`.
