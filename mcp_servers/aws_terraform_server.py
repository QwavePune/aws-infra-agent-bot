"""
AWS Terraform MCP Server

This MCP server provides tools for provisioning AWS infrastructure using Terraform.
It includes RBAC based on AWS IAM credentials and supports various infrastructure operations.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

from mcp_servers.aws_terraform import (
    AWSInfrastructureTemplates,
    AWSRBACManager,
    TerraformManager,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MCPAWSManagerServer:
    """MCP Server for AWS provisioning via Terraform or CLI"""
    
    def __init__(self):
        self.rbac = AWSRBACManager()
        self.terraform = TerraformManager(rbac_manager=self.rbac)
        self.templates = AWSInfrastructureTemplates()
        self.ecs_workflows: Dict[str, Dict[str, Any]] = {}

    def _reject_non_terraform_mode(self, mode: str) -> Optional[Dict[str, Any]]:
        if mode != "terraform":
            return {
                "success": False,
                "error": (
                    "CLI mode is decommissioned for safety and auditability. "
                    "Use mode='terraform' and continue with terraform_plan/terraform_apply."
                ),
            }
        return None

    def _ecs_missing_fields(self, config: Dict[str, Any]) -> List[str]:
        required = (
            "region",
            "cluster_name",
            "service_name",
            "container_image",
            "execution_role_arn",
            "task_role_arn",
            "subnet_ids",
            "security_group_ids",
        )
        missing = []
        for key in required:
            value = config.get(key)
            if value is None:
                missing.append(key)
                continue
            if isinstance(value, str) and not value.strip():
                missing.append(key)
                continue
            if isinstance(value, list) and len(value) == 0:
                missing.append(key)
        return missing

    def _build_config_review(self, project_name: str, config_text: str, preview_lines: int = 10) -> Dict[str, Any]:
        """Return compact config metadata to avoid huge single-line JSON payloads."""
        lines = config_text.splitlines()
        head = [line.rstrip() for line in lines[:preview_lines]]
        return {
            "main_tf_path": str(self.terraform.workspace_dir / project_name / "main.tf"),
            "line_count": len(lines),
            "char_count": len(config_text),
            "preview_head": head,
            "preview_truncated": len(lines) > preview_lines,
        }

    def _ecs_preflight_help(self, region: str) -> List[str]:
        """Return actionable commands for discovering valid ECS networking prerequisites."""
        return [
            f"aws ec2 describe-subnets --region {region} --query 'Subnets[].{{SubnetId:SubnetId,VpcId:VpcId,Az:AvailabilityZone}}' --output table",
            f"aws ec2 describe-security-groups --region {region} --query 'SecurityGroups[].{{GroupId:GroupId,VpcId:VpcId,Name:GroupName}}' --output table",
            "Use subnet_ids and security_group_ids from the same VPC.",
            "Use real IAM role ARNs for execution_role_arn and task_role_arn."
        ]

    def _questions_for_tool(self, tool_name: str, missing_fields: List[str]) -> List[str]:
        common_prompts = {
            "region": "Which AWS region should be used (for example: ap-south-1)?",
        }
        per_tool_prompts = {
            "create_s3_bucket": {
                "bucket_name": "What globally unique S3 bucket name should be created?",
            },
            "create_ec2_instance": {
                "instance_type": "Which EC2 instance type should be used (for example: t3.micro)?",
            },
            "create_vpc": {
                "cidr_block": "What VPC CIDR block should be used (for example: 10.0.0.0/16)?",
            },
            "create_rds_instance": {
                "db_name": "What database identifier/name should be used for the RDS instance?",
            },
            "create_lambda_function": {
                "function_name": "What Lambda function name should be created?",
            },
            "start_ecs_deployment_workflow": {
                "cluster_name": "What is the ECS cluster name?",
                "service_name": "What service name should we use?",
                "container_image": "What container image URI should be deployed (ECR/public image)?",
                "execution_role_arn": "What is the ECS task execution role ARN?",
                "task_role_arn": "What is the ECS task role ARN?",
                "subnet_ids": "Which subnet IDs should ECS tasks use? Provide at least one (same VPC).",
                "security_group_ids": "Which security group IDs should be attached to the service ENIs?",
            },
            "update_ecs_deployment_workflow": {
                "cluster_name": "What is the ECS cluster name?",
                "service_name": "What service name should we use?",
                "container_image": "What container image URI should be deployed (ECR/public image)?",
                "execution_role_arn": "What is the ECS task execution role ARN?",
                "task_role_arn": "What is the ECS task role ARN?",
                "subnet_ids": "Which subnet IDs should ECS tasks use? Provide at least one (same VPC).",
                "security_group_ids": "Which security group IDs should be attached to the service ENIs?",
            },
            "review_ecs_deployment_workflow": {
                "cluster_name": "What is the ECS cluster name?",
                "service_name": "What service name should we use?",
                "container_image": "What container image URI should be deployed (ECR/public image)?",
                "execution_role_arn": "What is the ECS task execution role ARN?",
                "task_role_arn": "What is the ECS task role ARN?",
                "subnet_ids": "Which subnet IDs should ECS tasks use? Provide at least one (same VPC).",
                "security_group_ids": "Which security group IDs should be attached to the service ENIs?",
            },
            "create_ecs_service": {
                "cluster_name": "What is the ECS cluster name?",
                "service_name": "What service name should we use?",
                "container_image": "What container image URI should be deployed (ECR/public image)?",
                "execution_role_arn": "What is the ECS task execution role ARN?",
                "task_role_arn": "What is the ECS task role ARN?",
                "subnet_ids": "Which subnet IDs should ECS tasks use? Provide at least one (same VPC).",
                "security_group_ids": "Which security group IDs should be attached to the service ENIs?",
            },
        }
        prompts = dict(common_prompts)
        prompts.update(per_tool_prompts.get(tool_name, {}))
        return [prompts[field] for field in missing_fields if field in prompts]

    def _validate_ecs_prereqs(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate ECS workflow prerequisites before terraform plan/apply."""
        region = config.get("region") or "us-east-1"
        subnet_ids = list(config.get("subnet_ids") or [])
        security_group_ids = list(config.get("security_group_ids") or [])
        execution_role_arn = config.get("execution_role_arn")
        task_role_arn = config.get("task_role_arn")

        validation = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "details": {
                "region": region,
                "subnet_ids": subnet_ids,
                "security_group_ids": security_group_ids,
            },
            "remediation": self._ecs_preflight_help(region),
        }

        subnet_vpcs: List[str] = []
        sg_vpcs: List[str] = []

        # Validate subnet IDs and capture VPC mapping.
        if subnet_ids:
            try:
                ec2 = boto3.client("ec2", region_name=region)
                subnets = ec2.describe_subnets(SubnetIds=subnet_ids).get("Subnets", [])
                found_subnet_ids = [s.get("SubnetId") for s in subnets if s.get("SubnetId")]
                missing_subnet_ids = sorted(set(subnet_ids) - set(found_subnet_ids))
                if missing_subnet_ids:
                    validation["errors"].append(f"Invalid or missing subnet IDs: {missing_subnet_ids}")

                subnet_vpcs = sorted({s.get("VpcId") for s in subnets if s.get("VpcId")})
                if len(subnet_vpcs) > 1:
                    validation["errors"].append(f"Subnets belong to multiple VPCs: {subnet_vpcs}")
                validation["details"]["subnet_vpcs"] = subnet_vpcs
            except ClientError as e:
                validation["errors"].append(f"Subnet validation failed: {str(e)}")
            except Exception as e:
                validation["warnings"].append(f"Could not fully validate subnets: {str(e)}")

        # Validate security groups and capture VPC mapping.
        if security_group_ids:
            try:
                ec2 = boto3.client("ec2", region_name=region)
                sgs = ec2.describe_security_groups(GroupIds=security_group_ids).get("SecurityGroups", [])
                found_sg_ids = [sg.get("GroupId") for sg in sgs if sg.get("GroupId")]
                missing_sg_ids = sorted(set(security_group_ids) - set(found_sg_ids))
                if missing_sg_ids:
                    validation["errors"].append(f"Invalid or missing security group IDs: {missing_sg_ids}")

                sg_vpcs = sorted({sg.get("VpcId") for sg in sgs if sg.get("VpcId")})
                if len(sg_vpcs) > 1:
                    validation["errors"].append(f"Security groups belong to multiple VPCs: {sg_vpcs}")
                validation["details"]["security_group_vpcs"] = sg_vpcs
            except ClientError as e:
                validation["errors"].append(f"Security group validation failed: {str(e)}")
            except Exception as e:
                validation["warnings"].append(f"Could not fully validate security groups: {str(e)}")

        # Cross-check subnet and security group VPCs.
        if len(subnet_vpcs) == 1 and len(sg_vpcs) == 1 and subnet_vpcs[0] != sg_vpcs[0]:
            validation["errors"].append(
                f"VPC mismatch: subnets are in {subnet_vpcs[0]} but security groups are in {sg_vpcs[0]}"
            )

        # Validate role ARNs by resolving role names.
        iam = None
        try:
            iam = boto3.client("iam")
        except Exception as e:
            validation["warnings"].append(f"Could not initialize IAM client for role validation: {str(e)}")

        def _check_role(role_arn: Optional[str], label: str):
            if not role_arn:
                return
            role_name = role_arn.split("role/")[-1].split("/")[-1]
            if not role_name:
                validation["errors"].append(f"{label} is not a valid IAM role ARN: {role_arn}")
                return
            if iam is None:
                return
            try:
                iam.get_role(RoleName=role_name)
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                if code in {"NoSuchEntity", "NoSuchEntityException"}:
                    validation["errors"].append(f"{label} does not exist: {role_arn}")
                elif code in {"AccessDenied", "AccessDeniedException"}:
                    validation["warnings"].append(
                        f"Access denied validating {label}; ensure role exists and is assumable: {role_arn}"
                    )
                else:
                    validation["warnings"].append(f"Could not validate {label}: {str(e)}")
            except Exception as e:
                validation["warnings"].append(f"Could not validate {label}: {str(e)}")

        _check_role(execution_role_arn, "execution_role_arn")
        _check_role(task_role_arn, "task_role_arn")

        validation["valid"] = len(validation["errors"]) == 0
        return validation
        
    def initialize(self) -> Dict[str, Any]:
        """Initialize the MCP server"""
        if not self.rbac.initialize():
            return {
                "success": False,
                "error": "Failed to initialize AWS credentials"
            }
        
        user_info = self.rbac.get_user_info()
        logger.info(f"MCP Server initialized for user: {user_info}")
        
        return {
            "success": True,
            "user_info": user_info,
            "message": "AWS Manager MCP Server initialized successfully. Creation tools use Terraform mode.",
            "preferred_method": "terraform"
        }
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """List available MCP tools"""
        return [
            {
                "name": "list_account_inventory",
                "description": "Read-only. Summarize AWS resources in the account across regions.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "regions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of AWS regions. If omitted, uses allowed regions."
                        }
                    }
                }
            },
            {
                "name": "get_cost_explorer_summary",
                "description": "Read-only. Get AWS Cost Explorer totals for a date range, optionally grouped by service.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start_date": {
                            "type": "string",
                            "description": "Inclusive start date in YYYY-MM-DD. Defaults to first day of current month."
                        },
                        "end_date": {
                            "type": "string",
                            "description": "Exclusive end date in YYYY-MM-DD. Defaults to tomorrow (UTC)."
                        },
                        "granularity": {
                            "type": "string",
                            "enum": ["DAILY", "MONTHLY"],
                            "description": "Granularity for Cost Explorer results. Defaults to MONTHLY."
                        },
                        "group_by_service": {
                            "type": "boolean",
                            "description": "Whether to include service-level cost breakdown. Defaults to true."
                        },
                        "metric": {
                            "type": "string",
                            "enum": ["UnblendedCost", "BlendedCost", "AmortizedCost", "NetUnblendedCost", "NetAmortizedCost"],
                            "description": "Cost metric to query. Defaults to UnblendedCost."
                        }
                    }
                }
            },
            {
                "name": "list_aws_resources",
                "description": "Read-only. List resources by type in a specific region.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "resource_type": {
                            "type": "string",
                            "enum": ["ec2", "vpc", "rds", "lambda", "s3", "ecs"],
                            "description": "Resource type to list (required)."
                        },
                        "region": {
                            "type": "string",
                            "description": "AWS region for regional services. Ignored for S3."
                        }
                    },
                    "required": ["resource_type"]
                }
            },
            {
                "name": "describe_resource",
                "description": "Read-only. Return details for a specific resource.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "resource_type": {
                            "type": "string",
                            "enum": ["ec2", "vpc", "rds", "lambda", "s3", "ecs"],
                            "description": "Resource type (required)."
                        },
                        "resource_id": {
                            "type": "string",
                            "description": "Resource identifier (instance id, vpc id, DB identifier, function name, bucket name)."
                        },
                        "region": {
                            "type": "string",
                            "description": "AWS region for regional services. Ignored for S3."
                        }
                    },
                    "required": ["resource_type", "resource_id"]
                }
            },
            {
                "name": "start_ecs_deployment_workflow",
                "description": "Start a guided ECS Fargate deployment workflow and return missing inputs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "region": {"type": "string", "description": "AWS region (for example ap-south-1)."},
                        "cluster_name": {"type": "string", "description": "ECS cluster name."},
                        "service_name": {"type": "string", "description": "ECS service name / task family name."},
                        "container_image": {"type": "string", "description": "Container image URI (ECR or public)."},
                        "execution_role_arn": {"type": "string", "description": "ECS task execution role ARN."},
                        "task_role_arn": {"type": "string", "description": "ECS task role ARN."},
                        "subnet_ids": {"type": "array", "items": {"type": "string"}, "description": "Subnets for awsvpc network mode."},
                        "security_group_ids": {"type": "array", "items": {"type": "string"}, "description": "Security groups for the service ENIs."},
                        "desired_count": {"type": "integer", "description": "Desired task count (default 1)."},
                        "container_port": {"type": "integer", "description": "Container port (default 8080)."},
                        "cpu": {"type": "integer", "description": "Task CPU units (default 256)."},
                        "memory": {"type": "integer", "description": "Task memory MB (default 512)."},
                        "assign_public_ip": {"type": "boolean", "description": "Assign public IP in awsvpc mode (default true)."}
                    }
                }
            },
            {
                "name": "update_ecs_deployment_workflow",
                "description": "Update an in-progress ECS deployment workflow with new inputs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "string", "description": "Workflow identifier returned by start_ecs_deployment_workflow."},
                        "region": {"type": "string"},
                        "cluster_name": {"type": "string"},
                        "service_name": {"type": "string"},
                        "container_image": {"type": "string"},
                        "execution_role_arn": {"type": "string"},
                        "task_role_arn": {"type": "string"},
                        "subnet_ids": {"type": "array", "items": {"type": "string"}},
                        "security_group_ids": {"type": "array", "items": {"type": "string"}},
                        "desired_count": {"type": "integer"},
                        "container_port": {"type": "integer"},
                        "cpu": {"type": "integer"},
                        "memory": {"type": "integer"},
                        "assign_public_ip": {"type": "boolean"}
                    },
                    "required": ["workflow_id"]
                }
            },
            {
                "name": "review_ecs_deployment_workflow",
                "description": "Review the ECS workflow config, show readiness/missing fields, and next action.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "string", "description": "Workflow identifier."}
                    },
                    "required": ["workflow_id"]
                }
            },
            {
                "name": "create_ecs_service",
                "description": "Create ECS Fargate Terraform project from workflow_id or direct parameters.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "string", "description": "Optional workflow identifier to source config from."},
                        "region": {"type": "string"},
                        "cluster_name": {"type": "string"},
                        "service_name": {"type": "string"},
                        "container_image": {"type": "string"},
                        "execution_role_arn": {"type": "string"},
                        "task_role_arn": {"type": "string"},
                        "subnet_ids": {"type": "array", "items": {"type": "string"}},
                        "security_group_ids": {"type": "array", "items": {"type": "string"}},
                        "desired_count": {"type": "integer"},
                        "container_port": {"type": "integer"},
                        "cpu": {"type": "integer"},
                        "memory": {"type": "integer"},
                        "assign_public_ip": {"type": "boolean"}
                    }
                }
            },
            {
                "name": "create_ec2_instance",
                "description": "Create an EC2 instance using Terraform",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "instance_type": {
                            "type": "string", 
                            "description": "EC2 instance type (default: t2.micro)"
                        },
                        "region": {
                            "type": "string",
                            "description": "AWS region (required, for example ap-south-1)"
                        },
                        "ami_id": {
                            "type": "string",
                            "description": "AMI ID (optional)"
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["terraform"],
                            "description": "Provisioning method (terraform only; default: terraform)"
                        }
                    },
                    "required": ["region"]
                }
            },
            {
                "name": "create_s3_bucket",
                "description": "Create an S3 bucket using Terraform.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "bucket_name": {
                            "type": "string",
                            "description": "S3 bucket name (required)"
                        },
                        "region": {
                            "type": "string",
                            "description": "AWS region (required, for example ap-south-1)"
                        },
                        "versioning": {
                            "type": "boolean",
                            "description": "Enable versioning (default: true)"
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["terraform"],
                            "description": "Provisioning method (terraform only; default: terraform)"
                        }
                    },
                    "required": ["bucket_name", "region"]
                }
            },
            {
                "name": "create_vpc",
                "description": "Create a VPC with subnets using Terraform",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "cidr_block": {
                            "type": "string",
                            "description": "VPC CIDR block (default: 10.0.0.0/16)"
                        },
                        "region": {
                            "type": "string",
                            "description": "AWS region (required, for example ap-south-1)"
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["terraform"],
                            "description": "Provisioning method (terraform only; default: terraform)"
                        }
                    },
                    "required": ["region"]
                }
            },
            {
                "name": "create_rds_instance",
                "description": "Create an RDS PostgreSQL instance using Terraform",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "db_name": {
                            "type": "string",
                            "description": "Database name (required)"
                        },
                        "instance_class": {
                            "type": "string",
                            "description": "RDS instance class (default: db.t3.micro)"
                        },
                        "region": {
                            "type": "string",
                            "description": "AWS region (required, for example ap-south-1)"
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["terraform"],
                            "description": "Provisioning method (terraform only; default: terraform)"
                        }
                    },
                    "required": ["db_name", "region"]
                }
            },
            {
                "name": "create_lambda_function",
                "description": "Create a Lambda function using Terraform",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "function_name": {
                            "type": "string",
                            "description": "Lambda function name (required)"
                        },
                        "region": {
                            "type": "string",
                            "description": "AWS region (required, for example ap-south-1)"
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["terraform"],
                            "description": "Provisioning method (terraform only; default: terraform)"
                        }
                    },
                    "required": ["function_name", "region"]
                }
            },
            {
                "name": "terraform_plan",
                "description": "Run terraform plan for a project",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "project_name": {
                            "type": "string",
                            "description": "Project directory name (required)"
                        }
                    },
                    "required": ["project_name"]
                }
            },
            {
                "name": "terraform_apply",
                "description": "Apply Terraform changes (will automatically approve if a plan file exists)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "project_name": {
                            "type": "string",
                            "description": "Project directory name (required)"
                        },
                        "auto_approve": {
                            "type": "boolean",
                            "description": "Auto-approve changes (default: true if tfplan exists)"
                        }
                    },
                    "required": ["project_name"]
                }
            },
            {
                "name": "terraform_destroy",
                "description": "Destroy Terraform-managed infrastructure",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "project_name": {
                            "type": "string",
                            "description": "Project directory name (required)"
                        },
                        "auto_approve": {
                            "type": "boolean",
                            "description": "Auto-approve destruction (default: false)"
                        }
                    },
                    "required": ["project_name"]
                }
            },
            {
                "name": "get_infrastructure_state",
                "description": "Get current infrastructure state",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "project_name": {
                            "type": "string",
                            "description": "Project directory name (required)"
                        }
                    },
                    "required": ["project_name"]
                }
            },
            {
                "name": "get_user_permissions",
                "description": "Get current AWS user permissions and info",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "parse_mermaid_architecture",
                "description": "Parse a Mermaid diagram to extract AWS architecture components and relationships",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "mermaid_content": {
                            "type": "string",
                            "description": "Mermaid diagram syntax (e.g., graph LR...)"
                        }
                    },
                    "required": ["mermaid_content"]
                }
            },
            {
                "name": "generate_terraform_from_architecture",
                "description": "Generate Terraform code from a parsed architecture",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "architecture": {
                            "type": "object",
                            "description": "Parsed architecture dict with resources and relationships"
                        }
                    },
                    "required": ["architecture"]
                }
            },
            {
                "name": "deploy_architecture",
                "description": "Generate and deploy AWS infrastructure from architecture (one-shot: generate + plan)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "architecture": {
                            "type": "object",
                            "description": "Parsed architecture dict with resources and relationships"
                        }
                    },
                    "required": ["architecture"]
                }
            },
            {
                "name": "list_aws_resources",
                "description": "List AWS resources in the account by type (ec2, s3, rds, lambda, vpc, etc.)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "resource_type": {
                            "type": "string",
                            "description": "AWS resource type to list (ec2_instances, s3_buckets, rds_instances, lambda_functions, vpcs, security_groups, subnets, etc.). If not specified, lists all resource types.",
                            "enum": ["ec2_instances", "s3_buckets", "rds_instances", "lambda_functions", "vpcs", "security_groups", "subnets", "iam_roles", "iam_policies", "dynamodb_tables", "all"]
                        },
                        "region": {
                            "type": "string",
                            "description": "AWS region to list resources from (default: current region)"
                        },
                        "filters": {
                            "type": "object",
                            "description": "Optional filters (e.g., {Name: value, Status: active})"
                        }
                    }
                }
            },
            {
                "name": "describe_resource",
                "description": "Get detailed information about a specific AWS resource",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "resource_id": {
                            "type": "string",
                            "description": "AWS resource ID, ARN, or name (required)"
                        },
                        "region": {
                            "type": "string",
                            "description": "AWS region (optional, will try to infer from ARN)"
                        }
                    },
                    "required": ["resource_id"]
                }
            },
            {
                "name": "list_account_inventory",
                "description": "Get a summary inventory of all AWS resources in the account across all regions",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "regions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of regions to scan (default: all available regions)"
                        },
                        "include_details": {
                            "type": "boolean",
                            "description": "Include detailed information for each resource (default: false)"
                        }
                    }
                }
            }
        ]
    
    def _list_aws_resources(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List AWS resources by type"""
        resource_type = params.get("resource_type", "all")
        region = params.get("region")
        filters = params.get("filters", {})
        
        try:
            session = boto3.Session()
            
            # Get region(s) to scan
            if region:
                regions_to_scan = [region]
            else:
                # Use current region or us-east-1
                regions_to_scan = [session.region_name or "us-east-1"]
            
            resources = {}
            
            # EC2 Instances
            if resource_type in ["ec2_instances", "all"]:
                instances_by_region = {}
                for reg in regions_to_scan:
                    try:
                        ec2_client = session.client("ec2", region_name=reg)
                        response = ec2_client.describe_instances()
                        instances = []
                        for reservation in response.get("Reservations", []):
                            for instance in reservation.get("Instances", []):
                                instances.append({
                                    "InstanceId": instance["InstanceId"],
                                    "InstanceType": instance["InstanceType"],
                                    "State": instance["State"]["Name"],
                                    "LaunchTime": instance["LaunchTime"].isoformat() if isinstance(instance["LaunchTime"], object) else str(instance["LaunchTime"]),
                                    "PublicIpAddress": instance.get("PublicIpAddress", "N/A"),
                                    "PrivateIpAddress": instance.get("PrivateIpAddress", "N/A"),
                                    "Tags": {tag["Key"]: tag["Value"] for tag in instance.get("Tags", [])}
                                })
                        if instances:
                            instances_by_region[reg] = instances
                    except Exception as e:
                        logger.warning(f"Failed to list EC2 instances in {reg}: {e}")
                if instances_by_region:
                    resources["ec2_instances"] = instances_by_region
            
            # S3 Buckets
            if resource_type in ["s3_buckets", "all"]:
                try:
                    s3_client = session.client("s3")
                    response = s3_client.list_buckets()
                    buckets = []
                    for bucket in response.get("Buckets", []):
                        buckets.append({
                            "BucketName": bucket["Name"],
                            "CreationDate": bucket["CreationDate"].isoformat() if isinstance(bucket["CreationDate"], object) else str(bucket["CreationDate"])
                        })
                    if buckets:
                        resources["s3_buckets"] = buckets
                except Exception as e:
                    logger.warning(f"Failed to list S3 buckets: {e}")
            
            # RDS Instances
            if resource_type in ["rds_instances", "all"]:
                rds_by_region = {}
                for reg in regions_to_scan:
                    try:
                        rds_client = session.client("rds", region_name=reg)
                        response = rds_client.describe_db_instances()
                        instances = []
                        for db in response.get("DBInstances", []):
                            instances.append({
                                "DBInstanceIdentifier": db["DBInstanceIdentifier"],
                                "DBInstanceClass": db["DBInstanceClass"],
                                "Engine": db["Engine"],
                                "DBInstanceStatus": db["DBInstanceStatus"],
                                "AllocatedStorage": db.get("AllocatedStorage", "N/A"),
                                "Endpoint": db.get("Endpoint", {}).get("Address", "N/A")
                            })
                        if instances:
                            rds_by_region[reg] = instances
                    except Exception as e:
                        logger.warning(f"Failed to list RDS instances in {reg}: {e}")
                if rds_by_region:
                    resources["rds_instances"] = rds_by_region
            
            # Lambda Functions
            if resource_type in ["lambda_functions", "all"]:
                lambda_by_region = {}
                for reg in regions_to_scan:
                    try:
                        lambda_client = session.client("lambda", region_name=reg)
                        response = lambda_client.list_functions()
                        functions = []
                        for func in response.get("Functions", []):
                            functions.append({
                                "FunctionName": func["FunctionName"],
                                "Runtime": func.get("Runtime", "N/A"),
                                "Handler": func.get("Handler", "N/A"),
                                "CodeSize": func.get("CodeSize", 0),
                                "LastModified": func.get("LastModified", "N/A")
                            })
                        if functions:
                            lambda_by_region[reg] = functions
                    except Exception as e:
                        logger.warning(f"Failed to list Lambda functions in {reg}: {e}")
                if lambda_by_region:
                    resources["lambda_functions"] = lambda_by_region
            
            # VPCs
            if resource_type in ["vpcs", "all"]:
                vpcs_by_region = {}
                for reg in regions_to_scan:
                    try:
                        ec2_client = session.client("ec2", region_name=reg)
                        response = ec2_client.describe_vpcs()
                        vpcs = []
                        for vpc in response.get("Vpcs", []):
                            vpcs.append({
                                "VpcId": vpc["VpcId"],
                                "CidrBlock": vpc["CidrBlock"],
                                "State": vpc["State"],
                                "IsDefault": vpc.get("IsDefault", False),
                                "Tags": {tag["Key"]: tag["Value"] for tag in vpc.get("Tags", [])}
                            })
                        if vpcs:
                            vpcs_by_region[reg] = vpcs
                    except Exception as e:
                        logger.warning(f"Failed to list VPCs in {reg}: {e}")
                if vpcs_by_region:
                    resources["vpcs"] = vpcs_by_region
            
            # Security Groups
            if resource_type in ["security_groups", "all"]:
                sg_by_region = {}
                for reg in regions_to_scan:
                    try:
                        ec2_client = session.client("ec2", region_name=reg)
                        response = ec2_client.describe_security_groups()
                        sgs = []
                        for sg in response.get("SecurityGroups", []):
                            sgs.append({
                                "GroupId": sg["GroupId"],
                                "GroupName": sg["GroupName"],
                                "Description": sg.get("Description", ""),
                                "VpcId": sg.get("VpcId", "N/A"),
                                "IngressRules": len(sg.get("IpPermissions", [])),
                                "EgressRules": len(sg.get("IpPermissionsEgress", []))
                            })
                        if sgs:
                            sg_by_region[reg] = sgs
                    except Exception as e:
                        logger.warning(f"Failed to list Security Groups in {reg}: {e}")
                if sg_by_region:
                    resources["security_groups"] = sg_by_region
            
            # Subnets
            if resource_type in ["subnets", "all"]:
                subnet_by_region = {}
                for reg in regions_to_scan:
                    try:
                        ec2_client = session.client("ec2", region_name=reg)
                        response = ec2_client.describe_subnets()
                        subnets = []
                        for subnet in response.get("Subnets", []):
                            subnets.append({
                                "SubnetId": subnet["SubnetId"],
                                "VpcId": subnet["VpcId"],
                                "CidrBlock": subnet["CidrBlock"],
                                "AvailabilityZone": subnet["AvailabilityZone"],
                                "AvailableIpAddressCount": subnet.get("AvailableIpAddressCount", 0)
                            })
                        if subnets:
                            subnet_by_region[reg] = subnets
                    except Exception as e:
                        logger.warning(f"Failed to list Subnets in {reg}: {e}")
                if subnet_by_region:
                    resources["subnets"] = subnet_by_region
            
            # IAM Roles
            if resource_type in ["iam_roles", "all"]:
                try:
                    iam_client = session.client("iam")
                    response = iam_client.list_roles()
                    roles = []
                    for role in response.get("Roles", []):
                        roles.append({
                            "RoleName": role["RoleName"],
                            "RoleId": role["RoleId"],
                            "Arn": role["Arn"],
                            "CreateDate": role["CreateDate"].isoformat() if isinstance(role["CreateDate"], object) else str(role["CreateDate"])
                        })
                    if roles:
                        resources["iam_roles"] = roles
                except Exception as e:
                    logger.warning(f"Failed to list IAM roles: {e}")
            
            # DynamoDB Tables
            if resource_type in ["dynamodb_tables", "all"]:
                dynamodb_by_region = {}
                for reg in regions_to_scan:
                    try:
                        dynamodb_client = session.client("dynamodb", region_name=reg)
                        response = dynamodb_client.list_tables()
                        tables = []
                        for table_name in response.get("TableNames", []):
                            tables.append({
                                "TableName": table_name
                            })
                        if tables:
                            dynamodb_by_region[reg] = tables
                    except Exception as e:
                        logger.warning(f"Failed to list DynamoDB tables in {reg}: {e}")
                if dynamodb_by_region:
                    resources["dynamodb_tables"] = dynamodb_by_region
            
            return {
                "success": True,
                "region": region or session.region_name or "us-east-1",
                "resources": resources,
                "resource_count": sum(
                    len(v) if isinstance(v, list) else sum(len(vv) for vv in v.values() if isinstance(vv, list))
                    for v in resources.values()
                )
            }
        
        except Exception as e:
            logger.error(f"Error listing AWS resources: {e}")
            return {
                "success": False,
                "error": f"Failed to list resources: {str(e)}"
            }
    
    def _describe_resource(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get detailed information about a specific AWS resource"""
        resource_id = params.get("resource_id")
        region = params.get("region")
        
        if not resource_id:
            return {"success": False, "error": "resource_id is required"}
        
        try:
            parsed = self._parse_resource_identifier(resource_id)
            
            session = boto3.Session()
            if not region:
                region = parsed.get("region") if parsed else (session.region_name or "us-east-1")
            
            # Determine resource type and fetch details
            if resource_id.startswith("i-"):
                # EC2 Instance
                ec2_client = session.client("ec2", region_name=region)
                response = ec2_client.describe_instances(InstanceIds=[resource_id])
                if response["Reservations"]:
                    instance = response["Reservations"][0]["Instances"][0]
                    return {
                        "success": True,
                        "resource_type": "EC2 Instance",
                        "resource_id": resource_id,
                        "details": {
                            "InstanceId": instance["InstanceId"],
                            "InstanceType": instance["InstanceType"],
                            "State": instance["State"]["Name"],
                            "LaunchTime": str(instance.get("LaunchTime")),
                            "PublicIpAddress": instance.get("PublicIpAddress", "N/A"),
                            "PrivateIpAddress": instance.get("PrivateIpAddress", "N/A"),
                            "SubnetId": instance.get("SubnetId"),
                            "VpcId": instance.get("VpcId"),
                            "SecurityGroups": [sg["GroupId"] for sg in instance.get("SecurityGroups", [])],
                            "Tags": {tag["Key"]: tag["Value"] for tag in instance.get("Tags", [])}
                        }
                    }
            
            elif resource_id.startswith("vpc-"):
                # VPC
                ec2_client = session.client("ec2", region_name=region)
                response = ec2_client.describe_vpcs(VpcIds=[resource_id])
                if response["Vpcs"]:
                    vpc = response["Vpcs"][0]
                    return {
                        "success": True,
                        "resource_type": "VPC",
                        "resource_id": resource_id,
                        "details": {
                            "VpcId": vpc["VpcId"],
                            "CidrBlock": vpc["CidrBlock"],
                            "State": vpc["State"],
                            "IsDefault": vpc.get("IsDefault", False),
                            "Tags": {tag["Key"]: tag["Value"] for tag in vpc.get("Tags", [])}
                        }
                    }
            
            elif resource_id.startswith("sg-"):
                # Security Group
                ec2_client = session.client("ec2", region_name=region)
                response = ec2_client.describe_security_groups(GroupIds=[resource_id])
                if response["SecurityGroups"]:
                    sg = response["SecurityGroups"][0]
                    return {
                        "success": True,
                        "resource_type": "Security Group",
                        "resource_id": resource_id,
                        "details": {
                            "GroupId": sg["GroupId"],
                            "GroupName": sg["GroupName"],
                            "Description": sg.get("Description", ""),
                            "VpcId": sg.get("VpcId", "N/A"),
                            "IngressRules": sg.get("IpPermissions", []),
                            "EgressRules": sg.get("IpPermissionsEgress", [])
                        }
                    }
            
            # Try S3 bucket
            elif not any(resource_id.startswith(prefix) for prefix in ["i-", "vpc-", "sg-", "subnet-", "ami-"]):
                try:
                    s3_client = session.client("s3")
                    s3_client.head_bucket(Bucket=resource_id)
                    response = s3_client.get_bucket_location(Bucket=resource_id)
                    return {
                        "success": True,
                        "resource_type": "S3 Bucket",
                        "resource_id": resource_id,
                        "details": {
                            "BucketName": resource_id,
                            "Region": response.get("LocationConstraint", "us-east-1")
                        }
                    }
                except:
                    pass
            
            return {
                "success": False,
                "error": f"Could not describe resource '{resource_id}'. Resource not found or type not supported."
            }
        
        except Exception as e:
            logger.error(f"Error describing resource: {e}")
            return {
                "success": False,
                "error": f"Failed to describe resource: {str(e)}"
            }
    
    def _list_account_inventory(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get a summary inventory of all AWS resources"""
        regions_param = params.get("regions")
        include_details = params.get("include_details", False)
        
        try:
            session = boto3.Session()
            
            # Get regions to scan
            if regions_param:
                regions_to_scan = regions_param
            else:
                try:
                    ec2_client = session.client("ec2")
                    response = ec2_client.describe_regions()
                    regions_to_scan = [region["RegionName"] for region in response["Regions"]]
                except:
                    regions_to_scan = [session.region_name or "us-east-1"]
            
            inventory = {
                "summary": {},
                "by_region": {},
                "timestamp": datetime.now().isoformat()
            }
            
            # Scan each region
            for region in regions_to_scan:
                region_resources = {}
                
                try:
                    ec2_client = session.client("ec2", region_name=region)
                    
                    # Count EC2 instances
                    response = ec2_client.describe_instances()
                    instance_count = sum(len(res["Instances"]) for res in response["Reservations"])
                    region_resources["ec2_instances"] = instance_count
                    
                    # Count VPCs
                    response = ec2_client.describe_vpcs()
                    region_resources["vpcs"] = len(response["Vpcs"])
                    
                    # Count Security Groups
                    response = ec2_client.describe_security_groups()
                    region_resources["security_groups"] = len(response["SecurityGroups"])
                    
                    # Count Subnets
                    response = ec2_client.describe_subnets()
                    region_resources["subnets"] = len(response["Subnets"])
                    
                    # RDS Instances
                    try:
                        rds_client = session.client("rds", region_name=region)
                        response = rds_client.describe_db_instances()
                        region_resources["rds_instances"] = len(response["DBInstances"])
                    except:
                        region_resources["rds_instances"] = 0
                    
                    # Lambda Functions
                    try:
                        lambda_client = session.client("lambda", region_name=region)
                        response = lambda_client.list_functions()
                        region_resources["lambda_functions"] = len(response["Functions"])
                    except:
                        region_resources["lambda_functions"] = 0
                    
                    # DynamoDB Tables
                    try:
                        dynamodb_client = session.client("dynamodb", region_name=region)
                        response = dynamodb_client.list_tables()
                        region_resources["dynamodb_tables"] = len(response["TableNames"])
                    except:
                        region_resources["dynamodb_tables"] = 0
                    
                except Exception as e:
                    logger.warning(f"Error scanning region {region}: {e}")
                    region_resources["error"] = str(e)
                
                if region_resources:
                    inventory["by_region"][region] = region_resources
            
            # Calculate global summary
            summary = {}
            for region_data in inventory["by_region"].values():
                for resource_type, count in region_data.items():
                    if resource_type != "error" and isinstance(count, int):
                        summary[resource_type] = summary.get(resource_type, 0) + count
            
            inventory["summary"] = summary
            inventory["total_resources"] = sum(summary.values())
            inventory["regions_scanned"] = len([r for r in inventory["by_region"] if "error" not in inventory["by_region"][r]])
            
            return {
                "success": True,
                "inventory": inventory
            }
        
        except Exception as e:
            logger.error(f"Error generating account inventory: {e}")
            return {
                "success": False,
                "error": f"Failed to generate inventory: {str(e)}"
            }
    
    def _parse_resource_identifier(self, resource_id: str) -> Optional[Dict[str, str]]:
        """
        Parse resource identifier to extract resource type and ID.
        
        Supports:
        - ARNs: arn:aws:ec2:region:account:instance/i-xxxxx
        - Resource IDs: i-xxxxx, vpc-xxxxx, bucket-name, etc.
        
        Returns:
            Dict with keys: resource_type, resource_id, region (if available)
            None if unable to parse
        """
        if not resource_id:
            return None
        
        # Handle ARN format
        if resource_id.startswith('arn:'):
            try:
                parts = resource_id.split(':')
                if len(parts) < 6:
                    return None
                
                service = parts[2]  # ec2, s3, rds, dynamodb, lambda, etc.
                region = parts[3]
                account = parts[4]
                resource_part = ':'.join(parts[5:])  # Handle resources with colons
                
                # Parse resource_part to extract resource type and ID
                # Examples:
                # instance/i-xxxxx -> (instance, i-xxxxx)
                # bucket/name -> (bucket, name)
                # table/name -> (table, name)
                
                if '/' in resource_part:
                    resource_type, resource_id_part = resource_part.split('/', 1)
                else:
                    # For some services like S3, it's just the bucket name
                    resource_type = 'bucket' if service == 's3' else 'unknown'
                    resource_id_part = resource_part
                
                return {
                    'service': service,
                    'resource_type': resource_type,
                    'resource_id': resource_id_part,
                    'region': region if region else None,
                    'account': account
                }
            except Exception as e:
                logger.warning(f"Failed to parse ARN: {resource_id}: {e}")
                return None
        
        # Handle resource ID patterns
        resource_patterns = {
            'i-': ('ec2', 'instance'),
            'vpc-': ('ec2', 'vpc'),
            'sg-': ('ec2', 'security-group'),
            'subnet-': ('ec2', 'subnet'),
            'nat-': ('ec2', 'nat-gateway'),
            'eni-': ('ec2', 'network-interface'),
            'vol-': ('ec2', 'volume'),
            'snap-': ('ec2', 'snapshot'),
            'ami-': ('ec2', 'image'),
            'rds-': ('rds', 'db-instance'),
            'arn:aws:rds:': ('rds', 'db-instance'),
            'lambda-': ('lambda', 'function'),
        }
        
        # Check if it's a known pattern
        for prefix, (service, resource_type) in resource_patterns.items():
            if resource_id.startswith(prefix):
                return {
                    'service': service,
                    'resource_type': resource_type,
                    'resource_id': resource_id,
                    'region': None,
                    'account': None
                }
        
        # If it doesn't match known patterns, it might be:
        # - S3 bucket name
        # - DynamoDB table name
        # - Lambda function name
        # - RDS instance name
        # Try to identify by checking AWS
        return None
    
    def _find_project_by_resource_id(self, resource_id: str) -> Optional[str]:
        """
        Find the Terraform project directory that manages a given AWS resource.
        
        Supports any AWS resource:
        - EC2 (instances, VPCs, security groups, etc.)
        - S3 buckets
        - RDS databases
        - DynamoDB tables
        - Lambda functions
        - And more...
        
        Args:
            resource_id: AWS resource identifier (ARN, resource ID, or name)
        
        Returns:
            Project directory name if found, None otherwise
        """
        if not resource_id:
            return None
        
        # Parse the resource identifier
        parsed = self._parse_resource_identifier(resource_id)
        
        logger.info(f"Searching for resource: {resource_id}")
        if parsed:
            logger.info(f"Parsed as: service={parsed.get('service')}, type={parsed.get('resource_type')}, id={parsed.get('resource_id')}")
        
        # Search through terraform state files for this resource
        workspace_dir = self.terraform.workspace_dir
        if not workspace_dir.exists():
            logger.warning(f"Workspace directory does not exist: {workspace_dir}")
            return None
        
        for project_dir in workspace_dir.iterdir():
            if not project_dir.is_dir():
                continue
            
            state_file = project_dir / "terraform.tfstate"
            if not state_file.exists():
                continue
            
            try:
                with open(state_file, 'r') as f:
                    state_data = json.load(f)
                
                # Check if this state file contains the resource
                resources = state_data.get('resources', [])
                for resource in resources:
                    resource_type = resource.get('type')
                    
                    # Check instances in this resource type
                    for instance in resource.get('instances', []):
                        attributes = instance.get('attributes', {})
                        
                        # Try multiple ways to match the resource:
                        # 1. By ID (e.g., instance ID, bucket name)
                        if attributes.get('id') == resource_id:
                            project_name = project_dir.name
                            logger.info(f"Found resource {resource_id} managed by project: {project_name} (matched by id)")
                            return project_name
                        
                        # 2. By ARN
                        if attributes.get('arn') == resource_id:
                            project_name = project_dir.name
                            logger.info(f"Found resource {resource_id} managed by project: {project_name} (matched by arn)")
                            return project_name
                        
                        # 3. For parsed resources, check specific attributes
                        if parsed:
                            resource_id_from_arn = parsed.get('resource_id')
                            
                            # Check by parsed resource ID
                            if attributes.get('id') == resource_id_from_arn:
                                project_name = project_dir.name
                                logger.info(f"Found resource {resource_id_from_arn} managed by project: {project_name} (matched by parsed id)")
                                return project_name
                            
                            # For S3 buckets, check bucket name
                            if parsed.get('service') == 's3' and attributes.get('bucket') == resource_id_from_arn:
                                project_name = project_dir.name
                                logger.info(f"Found S3 bucket {resource_id_from_arn} managed by project: {project_name}")
                                return project_name
                            
                            # For DynamoDB tables, check table name
                            if parsed.get('service') == 'dynamodb' and attributes.get('name') == resource_id_from_arn:
                                project_name = project_dir.name
                                logger.info(f"Found DynamoDB table {resource_id_from_arn} managed by project: {project_name}")
                                return project_name
                            
                            # For Lambda functions, check function name
                            if parsed.get('service') == 'lambda' and attributes.get('function_name') == resource_id_from_arn:
                                project_name = project_dir.name
                                logger.info(f"Found Lambda function {resource_id_from_arn} managed by project: {project_name}")
                                return project_name
                            
                            # For RDS instances, check identifier
                            if parsed.get('service') == 'rds' and attributes.get('identifier') == resource_id_from_arn:
                                project_name = project_dir.name
                                logger.info(f"Found RDS instance {resource_id_from_arn} managed by project: {project_name}")
                                return project_name
            
            except Exception as e:
                logger.debug(f"Error reading state file {state_file}: {e}")
                continue
        
        logger.warning(f"Resource {resource_id} not found in any Terraform state files")
        return None
    
    def _find_project_by_instance_id(self, instance_id: str, region: Optional[str] = None) -> Optional[str]:
        """
        Deprecated: Use _find_project_by_resource_id instead.
        Kept for backward compatibility.
        """
        return self._find_project_by_resource_id(instance_id)
    
    def _resolve_project_name(self, project_name: str) -> str:
        """
        Resolve project name by checking if it exists directly or with common prefixes.
        Also checks if the input is an AWS resource ID/ARN and finds the corresponding project.
        
        Supports:
        - Direct project names: 'ec2_t3.micro_ap-south-1'
        - Instance IDs: 'i-00ee2b589f0f4e455'
        - VPC IDs: 'vpc-xxxxx'
        - S3 buckets: 'bucket-name' or 'arn:aws:s3:::bucket-name'
        - RDS instances: 'db-instance-name'
        - DynamoDB tables: 'table-name'
        - ARNs: Full ARNs for any resource type
        - Abbreviated names: 't3.micro_ap-south-1' (tries 'ec2_' prefix)
        """
        if not project_name:
            return project_name
            
        # 1. Try exact match
        if (self.terraform.workspace_dir / project_name).exists():
            return project_name
            
        # 2. Try common prefixes
        prefixes = ["s3_", "ec2_", "vpc_", "rds_", "lambda_", "ecs_"]
        
        # 2. Check if it's an AWS resource ID or ARN (starts with common prefixes or 'arn:')
        if (project_name.startswith('i-') or 
            project_name.startswith('vpc-') or 
            project_name.startswith('sg-') or 
            project_name.startswith('subnet-') or 
            project_name.startswith('arn:aws:') or
            project_name.startswith('nat-') or
            project_name.startswith('eni-') or
            project_name.startswith('vol-') or
            project_name.startswith('snap-') or
            project_name.startswith('ami-') or
            project_name.startswith('rds-')):
            found_project = self._find_project_by_resource_id(project_name)
            if found_project:
                return found_project
        
        # 3. Try common prefixes for abbreviated names
        prefixes = ["s3_", "ec2_", "vpc_", "rds_", "lambda_", "dynamodb_"]
        for prefix in prefixes:
            if not project_name.startswith(prefix):
                candidate = f"{prefix}{project_name}"
                if (self.terraform.workspace_dir / candidate).exists():
                    logger.info(f"Resolved project '{project_name}' to '{candidate}'")
                    return candidate
        
        # 4. If none of the above worked, it might be a resource name (S3, DynamoDB, etc.)
        # Try searching by resource name as last resort
        found_project = self._find_project_by_resource_id(project_name)
        if found_project:
            return found_project
                    
        return project_name

    def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an MCP tool"""
        logger.info(f"Executing tool: {tool_name} with parameters: {parameters}")
        
        # Check if user is authenticated, try to initialize if not
        if not self.rbac.identity:
            logger.info("Identity not found, attempting to initialize AWS session...")
            if not self.rbac.initialize():
                return {
                    "success": False, 
                    "error": "User not authenticated. Please ensure you are logged in via AWS CLI and have the correct AWS_PROFILE set."
                }
        
        # Identity might be stale, but we'll try to use it. 
        # The individual handlers will catch permission errors.
        
        # Route to appropriate handler
        handlers = {
            "list_account_inventory": self._list_account_inventory,
            "get_cost_explorer_summary": self._get_cost_explorer_summary,
            "list_aws_resources": self._list_aws_resources,
            "describe_resource": self._describe_resource,
            "start_ecs_deployment_workflow": self._start_ecs_deployment_workflow,
            "update_ecs_deployment_workflow": self._update_ecs_deployment_workflow,
            "review_ecs_deployment_workflow": self._review_ecs_deployment_workflow,
            "create_ecs_service": self._create_ecs_service,
            "create_ec2_instance": self._create_ec2_instance,
            "create_s3_bucket": self._create_s3_bucket,
            "create_vpc": self._create_vpc,
            "create_rds_instance": self._create_rds_instance,
            "create_lambda_function": self._create_lambda_function,
            "terraform_plan": self._terraform_plan,
            "terraform_apply": self._terraform_apply,
            "terraform_destroy": self._terraform_destroy,
            "get_infrastructure_state": self._get_infrastructure_state,
            "get_user_permissions": self._get_user_permissions,
            "parse_mermaid_architecture": self._parse_mermaid_architecture,
            "generate_terraform_from_architecture": self._generate_terraform_from_architecture,
            "deploy_architecture": self._deploy_architecture,
        }
        
        handler = handlers.get(tool_name)
        if not handler:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        
        return handler(parameters)

    def _list_aws_resources(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Read-only resource listing by type."""
        resource_type = (params.get("resource_type") or "").lower()
        region = params.get("region") or os.getenv("AWS_REGION") or "us-east-1"

        try:
            if resource_type == "s3":
                s3 = boto3.client("s3")
                buckets = [{"name": b.get("Name"), "created": str(b.get("CreationDate"))} for b in s3.list_buckets().get("Buckets", [])]
                return {"success": True, "resource_type": "s3", "count": len(buckets), "items": buckets}

            if resource_type == "ec2":
                ec2 = boto3.client("ec2", region_name=region)
                reservations = ec2.describe_instances().get("Reservations", [])
                instances = []
                for r in reservations:
                    for i in r.get("Instances", []):
                        instances.append({
                            "instance_id": i.get("InstanceId"),
                            "state": i.get("State", {}).get("Name"),
                            "instance_type": i.get("InstanceType"),
                            "private_ip": i.get("PrivateIpAddress"),
                            "public_ip": i.get("PublicIpAddress"),
                        })
                return {"success": True, "resource_type": "ec2", "region": region, "count": len(instances), "items": instances}

            if resource_type == "vpc":
                ec2 = boto3.client("ec2", region_name=region)
                vpcs = [{
                    "vpc_id": v.get("VpcId"),
                    "cidr": v.get("CidrBlock"),
                    "state": v.get("State")
                } for v in ec2.describe_vpcs().get("Vpcs", [])]
                return {"success": True, "resource_type": "vpc", "region": region, "count": len(vpcs), "items": vpcs}

            if resource_type == "rds":
                rds = boto3.client("rds", region_name=region)
                dbs = [{
                    "db_identifier": d.get("DBInstanceIdentifier"),
                    "engine": d.get("Engine"),
                    "status": d.get("DBInstanceStatus"),
                    "class": d.get("DBInstanceClass")
                } for d in rds.describe_db_instances().get("DBInstances", [])]
                return {"success": True, "resource_type": "rds", "region": region, "count": len(dbs), "items": dbs}

            if resource_type == "lambda":
                lam = boto3.client("lambda", region_name=region)
                funcs = [{
                    "function_name": f.get("FunctionName"),
                    "runtime": f.get("Runtime"),
                    "last_modified": f.get("LastModified")
                } for f in lam.list_functions().get("Functions", [])]
                return {"success": True, "resource_type": "lambda", "region": region, "count": len(funcs), "items": funcs}

            if resource_type == "ecs":
                ecs = boto3.client("ecs", region_name=region)
                cluster_arns = ecs.list_clusters().get("clusterArns", [])
                clusters = []
                if cluster_arns:
                    described = ecs.describe_clusters(clusters=cluster_arns).get("clusters", [])
                    for c in described:
                        clusters.append({
                            "cluster_name": c.get("clusterName"),
                            "cluster_arn": c.get("clusterArn"),
                            "status": c.get("status"),
                            "running_tasks_count": c.get("runningTasksCount"),
                            "active_services_count": c.get("activeServicesCount"),
                        })
                return {"success": True, "resource_type": "ecs", "region": region, "count": len(clusters), "items": clusters}

            return {"success": False, "error": f"Unsupported resource_type '{resource_type}'"}
        except Exception as e:
            return {"success": False, "error": f"Failed to list {resource_type} resources: {str(e)}"}

    def _describe_resource(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Read-only resource details."""
        resource_type = (params.get("resource_type") or "").lower()
        resource_id = params.get("resource_id")
        region = params.get("region") or os.getenv("AWS_REGION") or "us-east-1"

        if not resource_id:
            return {"success": False, "error": "resource_id is required"}

        try:
            if resource_type == "s3":
                s3 = boto3.client("s3")
                location = s3.get_bucket_location(Bucket=resource_id).get("LocationConstraint") or "us-east-1"
                return {
                    "success": True,
                    "resource_type": "s3",
                    "resource_id": resource_id,
                    "details": {"bucket_name": resource_id, "region": location}
                }

            if resource_type == "ec2":
                ec2 = boto3.client("ec2", region_name=region)
                res = ec2.describe_instances(InstanceIds=[resource_id]).get("Reservations", [])
                if not res or not res[0].get("Instances"):
                    return {"success": False, "error": f"EC2 instance '{resource_id}' not found in {region}"}
                return {"success": True, "resource_type": "ec2", "region": region, "resource_id": resource_id, "details": res[0]["Instances"][0]}

            if resource_type == "vpc":
                ec2 = boto3.client("ec2", region_name=region)
                vpcs = ec2.describe_vpcs(VpcIds=[resource_id]).get("Vpcs", [])
                if not vpcs:
                    return {"success": False, "error": f"VPC '{resource_id}' not found in {region}"}
                return {"success": True, "resource_type": "vpc", "region": region, "resource_id": resource_id, "details": vpcs[0]}

            if resource_type == "rds":
                rds = boto3.client("rds", region_name=region)
                dbs = rds.describe_db_instances(DBInstanceIdentifier=resource_id).get("DBInstances", [])
                if not dbs:
                    return {"success": False, "error": f"RDS instance '{resource_id}' not found in {region}"}
                return {"success": True, "resource_type": "rds", "region": region, "resource_id": resource_id, "details": dbs[0]}

            if resource_type == "lambda":
                lam = boto3.client("lambda", region_name=region)
                func = lam.get_function(FunctionName=resource_id)
                return {"success": True, "resource_type": "lambda", "region": region, "resource_id": resource_id, "details": func.get("Configuration", {})}

            if resource_type == "ecs":
                ecs = boto3.client("ecs", region_name=region)
                # resource_id can be cluster name/arn or cluster/service tuple: cluster_name/service_name
                if "/" in resource_id and not resource_id.startswith("arn:"):
                    cluster_name, service_name = resource_id.split("/", 1)
                    service = ecs.describe_services(cluster=cluster_name, services=[service_name]).get("services", [])
                    if not service:
                        return {"success": False, "error": f"ECS service '{resource_id}' not found in {region}"}
                    return {
                        "success": True,
                        "resource_type": "ecs",
                        "region": region,
                        "resource_id": resource_id,
                        "details": service[0]
                    }

                cluster = ecs.describe_clusters(clusters=[resource_id]).get("clusters", [])
                if not cluster:
                    return {"success": False, "error": f"ECS cluster '{resource_id}' not found in {region}"}
                return {
                    "success": True,
                    "resource_type": "ecs",
                    "region": region,
                    "resource_id": resource_id,
                    "details": cluster[0]
                }

            return {"success": False, "error": f"Unsupported resource_type '{resource_type}'"}
        except Exception as e:
            return {"success": False, "error": f"Failed to describe {resource_type} resource '{resource_id}': {str(e)}"}

    def _list_account_inventory(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Read-only account inventory summary across regions."""
        regions = params.get("regions")
        if not regions:
            regions = self.rbac.get_allowed_regions()

        # Keep bounded for latency/safety in LLM loops.
        regions = list(regions)[:20]

        summary = {"ec2": 0, "vpc": 0, "rds": 0, "lambda": 0, "ecs": 0, "s3": 0}
        regional_breakdown = []

        # Global S3 count
        s3_result = self._list_aws_resources({"resource_type": "s3"})
        if s3_result.get("success"):
            summary["s3"] = s3_result.get("count", 0)

        for region in regions:
            region_counts = {"region": region, "ec2": 0, "vpc": 0, "rds": 0, "lambda": 0, "ecs": 0}
            for rtype in ("ec2", "vpc", "rds", "lambda", "ecs"):
                result = self._list_aws_resources({"resource_type": rtype, "region": region})
                if result.get("success"):
                    count = result.get("count", 0)
                    summary[rtype] += count
                    region_counts[rtype] = count
            regional_breakdown.append(region_counts)

        return {
            "success": True,
            "summary": summary,
            "regions_scanned": regions,
            "regional_breakdown": regional_breakdown
        }

    def _get_cost_explorer_summary(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Read-only AWS Cost Explorer summary for a date window."""
        params = params or {}
        granularity = (params.get("granularity") or "MONTHLY").upper()
        if granularity not in {"DAILY", "MONTHLY"}:
            return {"success": False, "error": "granularity must be DAILY or MONTHLY"}

        metric = params.get("metric") or "UnblendedCost"
        allowed_metrics = {"UnblendedCost", "BlendedCost", "AmortizedCost", "NetUnblendedCost", "NetAmortizedCost"}
        if metric not in allowed_metrics:
            return {"success": False, "error": f"metric must be one of: {', '.join(sorted(allowed_metrics))}"}

        try:
            today_utc = datetime.utcnow().date()
            default_start = today_utc.replace(day=1)
            default_end = today_utc + timedelta(days=1)  # Cost Explorer End is exclusive.

            start_date = datetime.strptime(params.get("start_date") or default_start.isoformat(), "%Y-%m-%d").date()
            end_date = datetime.strptime(params.get("end_date") or default_end.isoformat(), "%Y-%m-%d").date()
            if start_date >= end_date:
                return {"success": False, "error": "start_date must be earlier than end_date"}

            request: Dict[str, Any] = {
                "TimePeriod": {"Start": start_date.isoformat(), "End": end_date.isoformat()},
                "Granularity": granularity,
                "Metrics": [metric],
            }
            group_by_service = params.get("group_by_service", True)
            if group_by_service:
                request["GroupBy"] = [{"Type": "DIMENSION", "Key": "SERVICE"}]

            ce = boto3.client("ce", region_name="us-east-1")
            response = ce.get_cost_and_usage(**request)

            total_cost = 0.0
            currency = "USD"
            by_service: Dict[str, float] = {}
            periods = response.get("ResultsByTime", [])

            for period in periods:
                total_metric = period.get("Total", {}).get(metric, {})
                period_group_total = 0.0
                if total_metric:
                    total_cost += float(total_metric.get("Amount", "0") or 0.0)
                    currency = total_metric.get("Unit", currency) or currency

                for group in period.get("Groups", []):
                    service = (group.get("Keys") or ["Unknown"])[0]
                    metric_data = group.get("Metrics", {}).get(metric, {})
                    amount = float(metric_data.get("Amount", "0") or 0.0)
                    period_group_total += amount
                    by_service[service] = by_service.get(service, 0.0) + amount
                    currency = metric_data.get("Unit", currency) or currency

                # Cost Explorer commonly omits period Total when GroupBy is used.
                if not total_metric and period_group_total:
                    total_cost += period_group_total

            service_breakdown = [
                {"service": service, "amount": round(amount, 4), "currency": currency}
                for service, amount in sorted(by_service.items(), key=lambda x: x[1], reverse=True)
            ]

            return {
                "success": True,
                "start_date": start_date.isoformat(),
                "end_date_exclusive": end_date.isoformat(),
                "granularity": granularity,
                "metric": metric,
                "total_cost": {"amount": round(total_cost, 4), "currency": currency},
                "service_count": len(service_breakdown),
                "services": service_breakdown if group_by_service else [],
                "message": "Cost Explorer summary retrieved successfully."
            }
        except ValueError:
            return {"success": False, "error": "Invalid date format. Use YYYY-MM-DD for start_date/end_date."}
        except ClientError as e:
            return {"success": False, "error": f"Failed to query Cost Explorer: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error querying Cost Explorer: {str(e)}"}

    def _start_ecs_deployment_workflow(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Start a multi-turn ECS deployment workflow."""
        workflow_id = f"ecs-{uuid.uuid4().hex[:12]}"
        config = {
            "region": params.get("region"),
            "cluster_name": params.get("cluster_name"),
            "service_name": params.get("service_name"),
            "container_image": params.get("container_image"),
            "execution_role_arn": params.get("execution_role_arn"),
            "task_role_arn": params.get("task_role_arn"),
            "subnet_ids": params.get("subnet_ids") or [],
            "security_group_ids": params.get("security_group_ids") or [],
            "desired_count": params.get("desired_count", 1),
            "container_port": params.get("container_port", 8080),
            "cpu": params.get("cpu", 256),
            "memory": params.get("memory", 512),
            "assign_public_ip": params.get("assign_public_ip", True),
        }
        missing = self._ecs_missing_fields(config)
        preflight = self._validate_ecs_prereqs(config) if len(missing) == 0 else None
        self.ecs_workflows[workflow_id] = {"config": config}

        return {
            "success": True,
            "workflow_id": workflow_id,
            "workflow_type": "ecs_fargate",
            "config": config,
            "missing_fields": missing,
            "questions": self._questions_for_tool("start_ecs_deployment_workflow", missing),
            "preflight": preflight,
            "ready_to_create": len(missing) == 0 and bool(preflight and preflight.get("valid")),
            "next_action": "call create_ecs_service when ready" if not missing else "call update_ecs_deployment_workflow with missing fields",
        }

    def _update_ecs_deployment_workflow(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Update ECS workflow configuration with new values."""
        workflow_id = params.get("workflow_id")
        if not workflow_id:
            return {"success": False, "error": "workflow_id is required"}
        workflow = self.ecs_workflows.get(workflow_id)
        if not workflow:
            return {"success": False, "error": f"ECS workflow '{workflow_id}' not found"}

        config = workflow["config"]
        for key in (
            "region",
            "cluster_name",
            "service_name",
            "container_image",
            "execution_role_arn",
            "task_role_arn",
            "subnet_ids",
            "security_group_ids",
            "desired_count",
            "container_port",
            "cpu",
            "memory",
            "assign_public_ip",
        ):
            if key in params and params.get(key) is not None:
                config[key] = params.get(key)

        missing = self._ecs_missing_fields(config)
        preflight = self._validate_ecs_prereqs(config) if len(missing) == 0 else None
        return {
            "success": True,
            "workflow_id": workflow_id,
            "config": config,
            "missing_fields": missing,
            "questions": self._questions_for_tool("update_ecs_deployment_workflow", missing),
            "preflight": preflight,
            "ready_to_create": len(missing) == 0 and bool(preflight and preflight.get("valid")),
            "next_action": "call create_ecs_service" if not missing else "call update_ecs_deployment_workflow with remaining fields",
        }

    def _review_ecs_deployment_workflow(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Review current ECS workflow and provide deployment guidance."""
        workflow_id = params.get("workflow_id")
        if not workflow_id:
            return {"success": False, "error": "workflow_id is required"}
        workflow = self.ecs_workflows.get(workflow_id)
        if not workflow:
            return {"success": False, "error": f"ECS workflow '{workflow_id}' not found"}

        config = workflow["config"]
        missing = self._ecs_missing_fields(config)
        preflight = self._validate_ecs_prereqs(config) if len(missing) == 0 else None
        project_name = f"ecs_{(config.get('service_name') or 'service')}_{config.get('region')}"

        return {
            "success": True,
            "workflow_id": workflow_id,
            "ready_to_create": len(missing) == 0 and bool(preflight and preflight.get("valid")),
            "missing_fields": missing,
            "questions": self._questions_for_tool("review_ecs_deployment_workflow", missing),
            "preflight": preflight,
            "project_name": project_name,
            "plan": {
                "region": config.get("region"),
                "cluster_name": config.get("cluster_name"),
                "service_name": config.get("service_name"),
                "container_image": config.get("container_image"),
                "desired_count": config.get("desired_count"),
                "cpu": config.get("cpu"),
                "memory": config.get("memory"),
                "container_port": config.get("container_port"),
                "subnet_ids": config.get("subnet_ids"),
                "security_group_ids": config.get("security_group_ids"),
            },
            "next_action": "call create_ecs_service and then terraform_plan/terraform_apply" if not missing else "fill missing_fields using update_ecs_deployment_workflow",
            "safety_notes": [
                "This flow assumes existing VPC subnets and security groups.",
                "Review IAM role ARNs before apply.",
                "Fargate costs scale with desired_count, CPU, and memory."
            ]
        }

    def _create_ecs_service(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create ECS Fargate Terraform project from workflow or direct parameters."""
        if not self.rbac.check_permission("ecs:CreateCluster"):
            return {"success": False, "error": "User lacks ecs:CreateCluster permission"}
        if not self.rbac.check_permission("ecs:RegisterTaskDefinition"):
            return {"success": False, "error": "User lacks ecs:RegisterTaskDefinition permission"}
        if not self.rbac.check_permission("ecs:CreateService"):
            return {"success": False, "error": "User lacks ecs:CreateService permission"}

        workflow_id = params.get("workflow_id")
        if workflow_id:
            workflow = self.ecs_workflows.get(workflow_id)
            if not workflow:
                return {"success": False, "error": f"ECS workflow '{workflow_id}' not found"}
            config = dict(workflow["config"])
        else:
            config = {
                "region": params.get("region"),
                "cluster_name": params.get("cluster_name"),
                "service_name": params.get("service_name"),
                "container_image": params.get("container_image"),
                "execution_role_arn": params.get("execution_role_arn"),
                "task_role_arn": params.get("task_role_arn"),
                "subnet_ids": params.get("subnet_ids") or [],
                "security_group_ids": params.get("security_group_ids") or [],
                "desired_count": params.get("desired_count", 1),
                "container_port": params.get("container_port", 8080),
                "cpu": params.get("cpu", 256),
                "memory": params.get("memory", 512),
                "assign_public_ip": params.get("assign_public_ip", True),
            }

        missing = self._ecs_missing_fields(config)
        if missing:
            return {
                "success": False,
                "error": "Missing required ECS configuration fields",
                "missing_fields": missing,
                "questions": self._questions_for_tool("create_ecs_service", missing),
            }

        preflight = self._validate_ecs_prereqs(config)
        if not preflight.get("valid"):
            return {
                "success": False,
                "error": "ECS preflight validation failed. Fix invalid IDs/roles and retry create_ecs_service.",
                "preflight": preflight
            }

        project_name = f"ecs_{config['service_name']}_{config['region']}"
        project_path = self.terraform.workspace_dir / project_name
        project_path.mkdir(parents=True, exist_ok=True)

        tf_config = self.templates.ecs_fargate_service(
            region=config["region"],
            cluster_name=config["cluster_name"],
            service_name=config["service_name"],
            container_image=config["container_image"],
            execution_role_arn=config["execution_role_arn"],
            task_role_arn=config["task_role_arn"],
            subnet_ids=config["subnet_ids"],
            security_group_ids=config["security_group_ids"],
            container_port=int(config["container_port"]),
            desired_count=int(config["desired_count"]),
            cpu=int(config["cpu"]),
            memory=int(config["memory"]),
            assign_public_ip=bool(config["assign_public_ip"]),
        )
        (project_path / "main.tf").write_text(tf_config)

        init_result = self.terraform.init(project_name)
        if not init_result.get("success"):
            return init_result

        return {
            "success": True,
            "project_name": project_name,
            "workflow_id": workflow_id,
            "deployment_status": "initialized_not_applied",
            "preflight": preflight,
            "next_required_tools": [
                {"tool": "terraform_plan", "parameters": {"project_name": project_name}},
                {"tool": "terraform_apply", "parameters": {"project_name": project_name}}
            ],
            "message": (
                f"ECS service project created. Run terraform_plan with project_name='{project_name}', "
                f"then terraform_apply to deploy."
            ),
            "config_review": self._build_config_review(project_name, tf_config),
        }

    def _create_rds_instance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create RDS instance using Terraform."""
        db_name = params.get("db_name")
        instance_class = params.get("instance_class", "db.t3.micro")
        region = params.get("region")
        mode = params.get("mode", "terraform").lower() or "terraform"

        missing = []
        if not db_name:
            missing.append("db_name")
        if not region:
            missing.append("region")
        if missing:
            return {
                "success": False,
                "error": "Missing required fields for create_rds_instance",
                "missing_fields": missing,
                "questions": self._questions_for_tool("create_rds_instance", missing),
            }
        
        rejected = self._reject_non_terraform_mode(mode)
        if rejected:
            return rejected
            
        # Generate Terraform config (Default)
        project_name = f"rds_{db_name}"
        project_path = self.terraform.workspace_dir / project_name
        project_path.mkdir(parents=True, exist_ok=True)
        
        config = self.templates.rds_instance(db_name, instance_class, region)
        (project_path / "main.tf").write_text(config)
        
        init_result = self.terraform.init(project_name)
        if not init_result["success"]:
            return init_result
            
        return {
            "success": True,
            "project_name": project_name,
            "message": f"RDS instance project created. Run terraform_plan with project_name='{project_name}' to continue."
        }

    def _create_lambda_function(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create Lambda function using Terraform."""
        function_name = params.get("function_name")
        region = params.get("region")
        mode = params.get("mode", "terraform").lower() or "terraform"

        missing = []
        if not function_name:
            missing.append("function_name")
        if not region:
            missing.append("region")
        if missing:
            return {
                "success": False,
                "error": "Missing required fields for create_lambda_function",
                "missing_fields": missing,
                "questions": self._questions_for_tool("create_lambda_function", missing),
            }
        
        rejected = self._reject_non_terraform_mode(mode)
        if rejected:
            return rejected

        # Generate Terraform config
        project_name = f"lambda_{function_name}"
        project_path = self.terraform.workspace_dir / project_name
        project_path.mkdir(parents=True, exist_ok=True)
        
        config = self.templates.lambda_function(function_name, region)
        (project_path / "main.tf").write_text(config)
        
        # Create a dummy payload zip for Lambda
        import zipfile
        zip_path = project_path / "lambda_function_payload.zip"
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            zipf.writestr('index.py', 'def handler(event, context):\n    print("Hello from MCP Lambda!")\n    return {"statusCode": 200, "body": "Success"}')

        init_result = self.terraform.init(project_name)
        if not init_result["success"]:
            return init_result
            
        return {
            "success": True,
            "project_name": project_name,
            "message": f"Lambda function project created. Run terraform_plan with project_name='{project_name}' to continue."
        }
    
    def _create_ec2_instance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create EC2 instance using Terraform."""
        instance_type = params.get("instance_type", "t2.micro")
        region = params.get("region")
        ami_id = params.get("ami_id")
        mode = params.get("mode", "terraform").lower() or "terraform"

        missing = []
        if not region:
            missing.append("region")
        if missing:
            return {
                "success": False,
                "error": "Missing required fields for create_ec2_instance",
                "missing_fields": missing,
                "questions": self._questions_for_tool("create_ec2_instance", missing),
            }
        
        # Check permissions
        if not self.rbac.check_permission("ec2:RunInstances"):
            return {"success": False, "error": "User lacks ec2:RunInstances permission"}
        
        rejected = self._reject_non_terraform_mode(mode)
        if rejected:
            return rejected

        # Check for existing security group and reuse it
        existing_sg_id = self.rbac.get_existing_security_group("allow_ssh_http", region)
        sg_message = ""
        if existing_sg_id:
            sg_message = f" (reusing existing security group {existing_sg_id})"
        
        # Generate Terraform config
        project_name = f"ec2_{instance_type}_{region}"
        project_path = self.terraform.workspace_dir / project_name
        project_path.mkdir(parents=True, exist_ok=True)
        
        config = self.templates.ec2_instance(instance_type, ami_id, region, existing_sg_id)
        (project_path / "main.tf").write_text(config)
        
        # Initialize Terraform
        init_result = self.terraform.init(project_name)
        if not init_result["success"]:
            return init_result
        
        return {
            "success": True,
            "project_name": project_name,
            "message": f"EC2 instance project created{sg_message}. Run terraform_plan with project_name='{project_name}' to continue.",
            "config_review": self._build_config_review(project_name, config)
        }
    
    def _create_s3_bucket(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create S3 bucket using Terraform."""
        bucket_name = params.get("bucket_name")
        region = params.get("region")
        versioning = params.get("versioning", True)
        mode = params.get("mode", "terraform").lower() or "terraform"

        missing = []
        if not bucket_name:
            missing.append("bucket_name")
        if not region:
            missing.append("region")
        if missing:
            return {
                "success": False,
                "error": "Missing required fields for create_s3_bucket",
                "missing_fields": missing,
                "questions": self._questions_for_tool("create_s3_bucket", missing),
            }
        
        # Check permissions
        if not self.rbac.check_permission("s3:CreateBucket"):
            return {"success": False, "error": "User lacks s3:CreateBucket permission"}
        
        rejected = self._reject_non_terraform_mode(mode)
        if rejected:
            return rejected

        # Generate Terraform config
        project_name = f"s3_{bucket_name}"
        project_path = self.terraform.workspace_dir / project_name
        project_path.mkdir(parents=True, exist_ok=True)
        
        config = self.templates.s3_bucket(bucket_name, region, versioning)
        (project_path / "main.tf").write_text(config)
        
        # Initialize Terraform
        init_result = self.terraform.init(project_name)
        if not init_result["success"]:
            return init_result
        
        return {
            "success": True,
            "project_name": project_name,
            "message": f"S3 bucket project created. Run terraform_plan with project_name='{project_name}' to continue.",
            "config_review": self._build_config_review(project_name, config)
        }
    
    def _create_vpc(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create VPC using Terraform."""
        cidr_block = params.get("cidr_block", "10.0.0.0/16")
        region = params.get("region")
        mode = params.get("mode", "terraform").lower() or "terraform"

        missing = []
        if not region:
            missing.append("region")
        if missing:
            return {
                "success": False,
                "error": "Missing required fields for create_vpc",
                "missing_fields": missing,
                "questions": self._questions_for_tool("create_vpc", missing),
            }
        
        # Check permissions
        if not self.rbac.check_permission("ec2:CreateVpc"):
            return {"success": False, "error": "User lacks ec2:CreateVpc permission"}
        
        rejected = self._reject_non_terraform_mode(mode)
        if rejected:
            return rejected

        # Generate Terraform config
        project_name = f"vpc_{region}"
        project_path = self.terraform.workspace_dir / project_name
        project_path.mkdir(parents=True, exist_ok=True)
        
        config = self.templates.vpc_network(cidr_block, region)
        (project_path / "main.tf").write_text(config)
        
        # Initialize Terraform
        init_result = self.terraform.init(project_name)
        if not init_result["success"]:
            return init_result
        
        return {
            "success": True,
            "project_name": project_name,
            "message": f"VPC project created. Run terraform_plan with project_name='{project_name}' to continue.",
            "config_review": self._build_config_review(project_name, config)
        }
    
    def _terraform_plan(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Run terraform plan"""
        project_name = self._resolve_project_name(params.get("project_name"))
        if not project_name:
            return {"success": False, "error": "project_name is required"}
        
        return self.terraform.plan(project_name)
    
    def _terraform_apply(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Run terraform apply"""
        project_name = self._resolve_project_name(params.get("project_name"))
        if not project_name:
            return {"success": False, "error": "project_name is required"}
        
        auto_approve = params.get("auto_approve", False)
        return self.terraform.apply(project_name, auto_approve)
    
    def _terraform_destroy(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Run terraform destroy"""
        project_name = self._resolve_project_name(params.get("project_name"))
        if not project_name:
            return {"success": False, "error": "project_name is required"}
        
        # Default to auto_approve=True for convenience
        auto_approve = params.get("auto_approve", True)
        return self.terraform.destroy(project_name, auto_approve)
    
    def _get_infrastructure_state(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get infrastructure state"""
        project_name = self._resolve_project_name(params.get("project_name"))
        if not project_name:
            return {"success": False, "error": "project_name is required"}
        
        return self.terraform.show_state(project_name)
    
    def _get_user_permissions(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get user permissions"""
        user_info = self.rbac.get_user_info()
        regions = self.rbac.get_allowed_regions()
        
        return {
            "success": True,
            "user_info": user_info,
            "allowed_regions": regions
        }
    
    def _parse_mermaid_architecture(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Mermaid diagram to extract architecture"""
        from core.architecture_parser import ArchitectureParser
        
        mermaid_content = params.get("mermaid_content")
        if not mermaid_content:
            return {"success": False, "error": "mermaid_content is required"}
        
        try:
            parser = ArchitectureParser()
            result = parser.parse_mermaid_diagram(mermaid_content)
            result["success"] = True
            return result
        except Exception as e:
            logger.error(f"Error parsing mermaid: {e}")
            return {
                "success": False,
                "error": f"Failed to parse mermaid diagram: {str(e)}"
            }
    
    def _generate_terraform_from_architecture(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Generate Terraform code from parsed architecture"""
        from core.architecture_parser import ArchitectureParser
        
        architecture = params.get("architecture")
        if not architecture:
            return {"success": False, "error": "architecture dict is required"}
        
        try:
            # Try to get LLM instance for better code generation
            llm_instance = None
            try:
                from core.llm_config import initialize_llm
                llm_instance = initialize_llm("claude", temperature=0)
            except Exception as e:
                logger.warning(f"Could not initialize LLM for terraform generation: {e}")
            
            parser = ArchitectureParser(llm_provider="claude", llm_instance=llm_instance)
            result = parser.architecture_to_terraform(architecture)
            return result
        except Exception as e:
            logger.error(f"Error generating terraform: {e}")
            return {
                "success": False,
                "error": f"Failed to generate terraform: {str(e)}"
            }
    
    def _deploy_architecture(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Deploy architecture from parsed resources (generate + plan)"""
        from core.architecture_parser import ArchitectureParser
        
        architecture = params.get("architecture")
        if not architecture:
            return {"success": False, "error": "architecture dict is required"}
        
        try:
            # Generate Terraform
            llm_instance = None
            try:
                from core.llm_config import initialize_llm
                llm_instance = initialize_llm("claude", temperature=0)
            except Exception as e:
                logger.warning(f"Could not initialize LLM: {e}")
            
            parser = ArchitectureParser(llm_provider="claude", llm_instance=llm_instance)
            gen_result = parser.architecture_to_terraform(architecture)
            
            if not gen_result.get("success"):
                return gen_result
            
            project_name = gen_result.get("project_name")
            terraform_code = gen_result.get("terraform_code")
            
            # Save terraform code to file
            project_dir = self.terraform.workspace_dir / project_name
            project_dir.mkdir(parents=True, exist_ok=True)
            
            main_tf = project_dir / "main.tf"
            main_tf.write_text(terraform_code)
            
            logger.info(f"Terraform code saved to {project_dir}/main.tf")
            
            # Initialize and plan
            init_result = self.terraform.init(project_name)
            if not init_result.get("success"):
                return {
                    "success": False,
                    "error": "Terraform init failed",
                    "details": init_result,
                    "project_name": project_name
                }
            
            plan_result = self.terraform.plan(project_name)
            
            return {
                "success": plan_result.get("success", False),
                "project_name": project_name,
                "terraform_code": terraform_code,
                "plan_result": plan_result,
                "message": f"Infrastructure deployed and planned. Use terraform_apply to create resources."
            }
        
        except Exception as e:
            logger.error(f"Error deploying architecture: {e}")
            return {
                "success": False,
                "error": f"Failed to deploy architecture: {str(e)}"
            }


# Singleton instance
mcp_server = MCPAWSManagerServer()
