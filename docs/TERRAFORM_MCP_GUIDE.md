# AWS Terraform MCP Guide

This guide documents the implemented AWS MCP backend in this repository, not a generic future-state design.

## What The AWS MCP Server Actually Does

`mcp_servers/aws_terraform_server.py` exposes the tool contract used by the AGUI runtime and the CLI runtime.

It currently supports:

- read-only inventory and resource inspection
- Cost Explorer summaries
- guided ECS deployment workflow collection and validation
- Terraform-backed creation of EC2, S3, VPC, RDS, Lambda, and ECS resources
- Terraform plan, apply, destroy, and state inspection

## Why The Design Is Terraform-First

The server is intentionally Terraform-first for mutating AWS actions.

- `create_*` tools generate HCL and write to `terraform_workspace/<project_name>/main.tf`
- `terraform_plan` produces `tfplan`
- `terraform_apply` prefers applying the saved plan file
- `terraform_destroy` operates on the same project directory

This choice gives the system:

- a reviewable artifact on disk
- a stable project name that can be passed across tool calls
- a natural maker-checker review point
- better reproducibility than direct imperative CLI mutation

The code explicitly rejects older non-Terraform mutation modes.

## What Boto3 Still Does

Terraform is not the whole story. boto3 remains important in the AWS MCP layer for:

- STS caller identity
- IAM permission simulation
- allowed region discovery
- account inventory reads
- resource description
- ECS prerequisite validation for subnets, security groups, and IAM roles
- Cost Explorer queries

That split is intentional. Terraform handles durable infra changes; boto3 handles validation, discovery, and AWS context.

## Runtime Flow

1. The AGUI or CLI runtime binds the MCP tool schemas to the selected LLM.
2. The LLM emits a tool call.
3. The backend may block it due to read-only intent or maker-checker gating.
4. The AWS MCP server executes the allowed tool.
5. Terraform runs with credentials injected from the active boto3 session.
6. Results are returned to the runtime and surfaced to the user.

## Important Nuances

### Active Credentials

`AWSRBACManager.get_credentials_env()` freezes the current boto3 session credentials and passes them to Terraform subprocesses. `TerraformManager` removes `AWS_PROFILE` from the subprocess environment so explicit credentials win.

This is important because the UI supports client-scoped profile switching, and Terraform must follow the same effective identity.

### ECS Flow Is More Guarded Than The Simple Templates

The ECS toolchain is not a single blind template render. The server includes:

- `start_ecs_deployment_workflow`
- `update_ecs_deployment_workflow`
- `review_ecs_deployment_workflow`
- `create_ecs_service`

Before creation, the MCP server validates:

- subnet existence
- security group existence
- VPC consistency between subnets and security groups
- IAM role ARN plausibility and availability

This is one of the clearest examples of why the MCP layer exists as more than a thin Terraform wrapper.

### Plan-To-Apply Continuity

The AGUI backend keeps track of the last successfully planned project and can repair an incorrect `project_name` sent by the model to `terraform_apply` if a valid `tfplan` already exists for the last planned project.

That is an implementation-level reliability patch around LLM tool drift.

### Terraform State Is Local By Default

The generated projects in this repository do not automatically configure a remote backend. Unless a generated template includes one, Terraform state stays local to the workspace directory. This is fine for local operations and development, but it should be called out in any production review.

## Operational Requirements

- Terraform CLI installed and on `PATH`
- AWS credentials resolvable via the selected profile/session
- sufficient IAM permissions for both boto3 reads and Terraform actions
- writable local workspace for `terraform_workspace/`

## Related Files

- [aws_terraform_server.py](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/mcp_servers/aws_terraform_server.py)
- [terraform.py](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/mcp_servers/aws_terraform/terraform.py)
- [rbac.py](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/mcp_servers/aws_terraform/rbac.py)
- [templates.py](/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot/mcp_servers/aws_terraform/templates.py)
