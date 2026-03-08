# Architecture-Driven Deployment Implementation

This note documents the implementation details of the architecture-driven path without overstating its scope.

## Implemented Components

### `core/architecture_parser.py`

Implements:

- `parse_mermaid_diagram(mermaid_content)`
- `parse_architecture_image(image_path)`
- `architecture_to_terraform(architecture)`

The parser does two very different jobs:

- lightweight Mermaid node/edge extraction through regex
- LLM-backed vision analysis and Terraform generation

That means the module is useful, but it should not be described as a deterministic architecture compiler.

### `bin/agui_server.py`

Adds four REST endpoints:

- `POST /api/architecture/parse-mermaid`
- `POST /api/architecture/parse-image`
- `POST /api/architecture/generate-terraform`
- `POST /api/architecture/deploy`

The deploy endpoint writes the generated `main.tf` to the same `terraform_workspace/` used by the AWS MCP server and then attempts `terraform init` and `terraform plan`.

### `ui/architecture-deployment.js`

Provides a frontend helper library and demo components for the architecture endpoints. It is an integration helper, not the main UI used by `ui/index.html`.

## What Is Not Implemented

- There are no dedicated architecture MCP tools in the current `mcp_servers/aws_terraform_server.py`.
- The AGUI chat flow does not route through special architecture tools before normal MCP execution.
- The architecture-driven endpoints do not integrate with the richer maker-checker flow built around `/api/run`.

## Review Perspective

This path is best treated as:

- an auxiliary diagram-to-IaC accelerator
- useful for prototyping and demos
- less operationally complete than the main chat runtime

For the system-wide view, use [SYSTEM_ARCHITECTURE.md](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/docs/SYSTEM_ARCHITECTURE.md).
