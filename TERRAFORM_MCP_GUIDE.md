# AWS Infrastructure Agent - Terraform MCP Guide

This project now includes a Model Context Protocol (MCP) server for AWS Infrastructure provisioning via Terraform.

## Features
- **Natural Language Infrastructure**: "Create an m5.large instance in us-west-2"
- **RBAC Integration**: Automatically checks your AWS IAM permissions using the IAM Policy Simulator.
- **Terraform Automation**: Handles the full lifecycle of infrastructure (Init -> Plan -> Apply).
- **Pre-built Templates**: Optimized patterns for EC2, S3, and VPC.

## Prerequisites
1. **Terraform CLI**: Must be installed and available in the system PATH.
2. **AWS Credentials**: Must be configured (via `~/.aws/credentials`, Environment Variables, or the Project Keychain).
3. **IAM Permissions**: The user must have sufficient permissions to simulate policies and manage resources.

## Usage
1. Start the server: `python3 agui_server.py`
2. Open the UI: [http://localhost:8000](http://localhost:8000)
3. Select **"AWS Infrastructure (Terraform)"** from the MCP Server dropdown in the header.
4. Select your preferred LLM (e.g., OpenAI or Claude).
5. Ask the agent to build something:
   - *"Provision a public S3 bucket named my-company-data-exports in us-east-1"*
   - *"Set up a VPC with public and private subnets"*
   - *"Deploy a t2.micro instance for testing"*

## How it Works
1. **Tool Binding**: When you select the MCP server, the backend retrieves a list of infrastructure tools from the `MCPAWSTerraformServer`.
2. **LLM Invocation**: The LLM (LangChain) is "bound" with these tools.
3. **Execution Loop**:
   - The LLM outputs a tool call (e.g., `create_s3_bucket`).
   - The backend executes the tool via the MCP server.
   - The MCP server generates Terraform HCL, runs `terraform init`, and prepares the project.
   - The result is sent back to the LLM.
4. **Conversational Feedback**: The LLM confirms the operation and provides details (like public IPs or bucket names).

## Security & RBAC
- **Credential Source**: Uses the project's centralized `llm_config.py` logic to source AWS credentials.
- **Simulation First**: Before running Terraform, the MCP server calls `iam:SimulatePrincipalPolicy` to ensure the user is authorized.
- **Safe State**: Terraform state and project files are managed in `./terraform_workspace/`.

## Troubleshooting
- **"Terraform not found"**: Ensure the `terraform` binary is installed (`brew install terraform` on macOS).
- **"Unauthorized"**: Check your AWS credentials and ensure you have permissions to the resources you are trying to create.
- **Logs**: Monitor `agui-server.log` for detailed execution logs of both the LLM and the Terraform commands.
