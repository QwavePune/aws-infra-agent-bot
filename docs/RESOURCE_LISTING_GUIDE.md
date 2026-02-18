# AWS Resource Listing Guide

## Overview

The AWS Infrastructure Agent now supports comprehensive AWS resource discovery and listing capabilities through three new tools available in the AGUI server:

1. **`list_aws_resources`** - List resources by type
2. **`describe_resource`** - Get detailed information about a specific resource
3. **`list_account_inventory`** - Get a complete account inventory across regions

## Available Tools

### 1. List AWS Resources by Type

**Tool Name:** `list_aws_resources`

**Description:** List AWS resources in the account by type

**Parameters:**
- `resource_type` (optional): Type of resource to list
  - Supported values: `ec2_instances`, `s3_buckets`, `rds_instances`, `lambda_functions`, `vpcs`, `security_groups`, `subnets`, `iam_roles`, `iam_policies`, `dynamodb_tables`, `all`
  - Default: `all` (lists all supported resource types)
- `region` (optional): AWS region to list resources from
  - If not specified, uses the current region
- `filters` (optional): Filter criteria (e.g., `{Name: value, Status: active}`)

**Example Usage:**

```bash
# List all EC2 instances in the current region
curl -X POST http://localhost:9595/api/mcp/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "list_aws_resources",
    "parameters": {
      "resource_type": "ec2_instances"
    }
  }'

# List all S3 buckets
curl -X POST http://localhost:9595/api/mcp/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "list_aws_resources",
    "parameters": {
      "resource_type": "s3_buckets"
    }
  }'

# List all Lambda functions in us-west-2
curl -X POST http://localhost:9595/api/mcp/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "list_aws_resources",
    "parameters": {
      "resource_type": "lambda_functions",
      "region": "us-west-2"
    }
  }'

# List all resources (EC2, S3, RDS, Lambda, VPCs, etc.)
curl -X POST http://localhost:9595/api/mcp/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "list_aws_resources",
    "parameters": {
      "resource_type": "all"
    }
  }'
```

**Response Example:**

```json
{
  "success": true,
  "region": "us-east-1",
  "resources": {
    "ec2_instances": {
      "us-east-1": [
        {
          "InstanceId": "i-0abc123def456",
          "InstanceType": "t3.micro",
          "State": "running",
          "LaunchTime": "2024-02-15T10:30:00",
          "PublicIpAddress": "52.123.45.67",
          "PrivateIpAddress": "10.0.1.100",
          "Tags": {
            "Name": "my-app-server",
            "Environment": "production"
          }
        }
      ]
    },
    "s3_buckets": [
      {
        "BucketName": "my-data-bucket",
        "CreationDate": "2023-01-15T08:00:00"
      },
      {
        "BucketName": "my-logs-bucket",
        "CreationDate": "2023-02-20T14:30:00"
      }
    ]
  },
  "resource_count": 3
}
```

### 2. Describe a Specific Resource

**Tool Name:** `describe_resource`

**Description:** Get detailed information about a specific AWS resource

**Parameters:**
- `resource_id` (required): AWS resource ID, ARN, or name
  - Examples: `i-0abc123def456`, `vpc-12345678`, `sg-87654321`, `my-bucket-name`, `my-function`
- `region` (optional): AWS region (will try to infer from ARN if not provided)

**Supported Resource Types:**
- EC2 Instances (ID starts with `i-`)
- VPCs (ID starts with `vpc-`)
- Security Groups (ID starts with `sg-`)
- S3 Buckets (by name)
- And more...

**Example Usage:**

```bash
# Describe a specific EC2 instance
curl -X POST http://localhost:9595/api/mcp/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "describe_resource",
    "parameters": {
      "resource_id": "i-0abc123def456"
    }
  }'

# Describe a VPC
curl -X POST http://localhost:9595/api/mcp/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "describe_resource",
    "parameters": {
      "resource_id": "vpc-12345678"
    }
  }'

# Describe a security group
curl -X POST http://localhost:9595/api/mcp/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "describe_resource",
    "parameters": {
      "resource_id": "sg-87654321",
      "region": "us-west-2"
    }
  }'

# Describe an S3 bucket
curl -X POST http://localhost:9595/api/mcp/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "describe_resource",
    "parameters": {
      "resource_id": "my-bucket-name"
    }
  }'
```

**Response Example:**

```json
{
  "success": true,
  "resource_type": "EC2 Instance",
  "resource_id": "i-0abc123def456",
  "details": {
    "InstanceId": "i-0abc123def456",
    "InstanceType": "t3.micro",
    "State": "running",
    "LaunchTime": "2024-02-15T10:30:00",
    "PublicIpAddress": "52.123.45.67",
    "PrivateIpAddress": "10.0.1.100",
    "SubnetId": "subnet-12345678",
    "VpcId": "vpc-87654321",
    "SecurityGroups": ["sg-11111111", "sg-22222222"],
    "Tags": {
      "Name": "my-app-server",
      "Environment": "production"
    }
  }
}
```

### 3. List Account Inventory

**Tool Name:** `list_account_inventory`

**Description:** Get a summary inventory of all AWS resources in the account across all regions

**Parameters:**
- `regions` (optional): List of regions to scan
  - If not specified, scans all available AWS regions
  - Example: `["us-east-1", "us-west-2", "ap-south-1"]`
- `include_details` (optional): Include detailed information for each resource
  - Default: `false` (summary only)

**Example Usage:**

```bash
# Get account inventory for all regions
curl -X POST http://localhost:9595/api/mcp/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "list_account_inventory",
    "parameters": {}
  }'

# Get inventory for specific regions
curl -X POST http://localhost:9595/api/mcp/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "list_account_inventory",
    "parameters": {
      "regions": ["us-east-1", "us-west-2", "eu-west-1"]
    }
  }'

# Get inventory with detailed information
curl -X POST http://localhost:9595/api/mcp/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "list_account_inventory",
    "parameters": {
      "regions": ["us-east-1", "us-west-2"],
      "include_details": true
    }
  }'
```

**Response Example:**

```json
{
  "success": true,
  "inventory": {
    "summary": {
      "ec2_instances": 5,
      "vpcs": 2,
      "security_groups": 8,
      "subnets": 6,
      "rds_instances": 1,
      "lambda_functions": 12,
      "dynamodb_tables": 3,
      "s3_buckets": 4
    },
    "by_region": {
      "us-east-1": {
        "ec2_instances": 3,
        "vpcs": 1,
        "security_groups": 5,
        "subnets": 3,
        "rds_instances": 1,
        "lambda_functions": 8,
        "dynamodb_tables": 2
      },
      "us-west-2": {
        "ec2_instances": 2,
        "vpcs": 1,
        "security_groups": 3,
        "subnets": 3,
        "rds_instances": 0,
        "lambda_functions": 4,
        "dynamodb_tables": 1
      }
    },
    "timestamp": "2024-02-16T14:30:45.123456",
    "total_resources": 41,
    "regions_scanned": 2
  }
}
```

## Using in the AGUI UI

The new resource listing tools are accessible through the AGUI web interface:

1. **Open the AGUI server:**
   ```bash
   cd /Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot
   python3 bin/agui_server.py
   ```

2. **Navigate to:** `http://localhost:9595`

3. **Select MCP Mode:** Choose "AWS Manager (MCP)" from the MCP Server dropdown

4. **Use the Resource Listing Tools:**
   - In the tool parameters section, select `list_aws_resources`, `describe_resource`, or `list_account_inventory`
   - Fill in the required parameters
   - Click "Execute Tool"

## CLI Usage Example

You can also use these tools from the CLI agent:

```bash
python3 bin/langchain-agent.py
```

When prompted for a query, you can ask the agent to:

```
"List all EC2 instances in the account"
"Show me details about instance i-0abc123def456"
"Give me an inventory of all resources in us-east-1 and us-west-2"
"List all S3 buckets"
```

The agent will automatically select the appropriate tool and execute it.

## Error Handling

All tools return a consistent response format:

```json
{
  "success": false,
  "error": "Error message describing what went wrong"
}
```

Common error scenarios:
- **AWS Credentials Not Found:** Ensure AWS CLI is configured (`aws configure`)
- **Insufficient Permissions:** Check IAM permissions for the user/role
- **Invalid Region:** Specify a valid AWS region
- **Invalid Resource ID:** Double-check the resource ID format

## Requirements

- AWS credentials configured via AWS CLI (`aws configure`)
- Proper IAM permissions to describe resources:
  - `ec2:Describe*` for EC2 resources
  - `s3:ListAllMyBuckets` for S3 buckets
  - `rds:DescribeDBInstances` for RDS databases
  - `lambda:ListFunctions` for Lambda functions
  - `dynamodb:ListTables` for DynamoDB tables
  - `iam:ListRoles` for IAM roles

## Performance Considerations

- **`list_account_inventory`** can take 1-2 minutes if scanning all regions
- **`list_aws_resources`** with `resource_type: "all"` scans all resource types (slower)
- Specify specific resource types or regions for faster results
- S3 buckets are global, so they're only listed once regardless of region parameter

## Next Steps

- Use `describe_resource` to get details about specific resources you want to manage
- Use `list_account_inventory` to generate infrastructure documentation
- Combine with Terraform provisioning tools to manage discovered resources
- Use resource IDs with `terraform_destroy` to delete specific resources
