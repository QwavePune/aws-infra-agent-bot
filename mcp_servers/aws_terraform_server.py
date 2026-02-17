"""
AWS Terraform MCP Server

This MCP server provides tools for provisioning AWS infrastructure using Terraform.
It includes RBAC based on AWS IAM credentials and supports various infrastructure operations.
"""

import json
import os
import subprocess
import logging
import uuid
import re
from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


class AWSRBACManager:
    """Manages AWS RBAC using IAM credentials and policies"""
    
    def __init__(self):
        self.sts_client = None
        self.iam_client = None
        self.identity = None
        
    def initialize(self):
        """Initialize AWS clients and get caller identity"""
        try:
            # Explicitly log environment context for debugging
            profile = os.environ.get('AWS_PROFILE', 'default')
            region = os.environ.get('AWS_REGION', os.environ.get('AWS_DEFAULT_REGION', 'not set'))
            logger.info(f"Initializing AWS Session (Profile: {profile}, Region: {region})")
            
            session = boto3.Session()
            self.sts_client = session.client('sts')
            self.iam_client = session.client('iam')
            self.identity = self.sts_client.get_caller_identity()
            
            logger.info(f"AWS Identity Successfully Retrieved: {self.identity.get('Arn')}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize AWS clients: {str(e)}")
            self.identity = None
            return False

    def get_credentials_env(self) -> Dict[str, str]:
        """Get active AWS credentials as environment variables for subprocesses"""
        try:
            session = boto3.Session()
            creds = session.get_credentials()
            if not creds:
                return {}
            
            frozen = creds.get_frozen_credentials()
            env = {
                "AWS_ACCESS_KEY_ID": frozen.access_key,
                "AWS_SECRET_ACCESS_KEY": frozen.secret_key,
            }
            if frozen.token:
                env["AWS_SESSION_TOKEN"] = frozen.token
                
            region = session.region_name or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
            if region:
                env["AWS_REGION"] = region
                env["AWS_DEFAULT_REGION"] = region
                
            return env
        except Exception as e:
            logger.warning(f"Could not extract session credentials: {e}")
            return {}
    
    def get_user_info(self) -> Dict[str, Any]:
        """Get current AWS user information"""
        if not self.identity:
            if not self.initialize():
                return {
                    "account_id": "unknown (no credentials)",
                    "user_arn": "unknown",
                    "user_id": "unknown",
                    "error": "Failed to initialize AWS Session"
                }
        
        return {
            "account_id": self.identity.get("Account", "unknown"),
            "user_arn": self.identity.get("Arn", "unknown"),
            "user_id": self.identity.get("UserId", "unknown")
        }
    
    def check_permission(self, action: str, resource: str = "*") -> bool:
        """
        Check if the current user has permission for a specific action
        
        Args:
            action: AWS action (e.g., 'ec2:RunInstances')
            resource: AWS resource ARN
        
        Returns:
            bool: True if user has permission
        """
        try:
            # Root user check - SimulatePrincipalPolicy doesn't support the root user ARN
            if self.identity and self.identity.get("Arn") and ":root" in self.identity["Arn"]:
                logger.info("Root user detected, skipping permission check (Full Access)")
                return True

            # Use IAM policy simulator to check permissions
            response = self.iam_client.simulate_principal_policy(
                PolicySourceArn=self.identity["Arn"],
                ActionNames=[action],
                ResourceArns=[resource]
            )
            
            for result in response.get("EvaluationResults", []):
                if result["EvalDecision"] == "allowed":
                    return True
            
            return False
        except Exception as e:
            logger.warning(f"Permission check failed: {e}")
            # Default to allowing if check fails (most common for restricted accounts or Root)
            return True
    
    def get_allowed_regions(self) -> List[str]:
        """Get list of AWS regions the user can access"""
        try:
            ec2_client = boto3.client('ec2')
            response = ec2_client.describe_regions()
            return [region['RegionName'] for region in response['Regions']]
        except Exception as e:
            logger.error(f"Failed to get regions: {e}")
            return ["us-east-1"]  # Default fallback
    
    def get_existing_security_group(self, sg_name: str, region: str) -> Optional[str]:
        """
        Query for an existing security group by name in a region.
        
        Args:
            sg_name: Security group name to search for
            region: AWS region
            
        Returns:
            Security group ID if found, None otherwise
        """
        try:
            ec2_client = boto3.client('ec2', region_name=region)
            response = ec2_client.describe_security_groups(
                Filters=[{'Name': 'group-name', 'Values': [sg_name]}]
            )
            
            if response.get('SecurityGroups'):
                sg_id = response['SecurityGroups'][0]['GroupId']
                logger.info(f"Found existing security group '{sg_name}' in {region}: {sg_id}")
                return sg_id
            
            logger.debug(f"No existing security group '{sg_name}' found in {region}")
            return None
        except Exception as e:
            logger.warning(f"Error querying security groups in {region}: {e}")
            return None


class TerraformManager:
    """Manages Terraform operations"""
    
    def __init__(self, workspace_dir: str = "./terraform_workspace", rbac_manager=None):
        self.workspace_dir = Path(workspace_dir)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.rbac = rbac_manager
        
    def _run_terraform(self, cmd: List[str], cwd: Path) -> Dict[str, Any]:
        """Run terraform command with inherited environment and explicit credentials"""
        try:
            # Inherit current env and overlay with active session credentials
            env = os.environ.copy()
            if self.rbac:
                creds = self.rbac.get_credentials_env()
                env.update(creds)
                if "AWS_PROFILE" in env:
                    # Remove AWS_PROFILE to ensure injected credentials are used
                    del env["AWS_PROFILE"]
            
            logger.info(f"EXECUTION: Real AWS Provisioning - Running command: {' '.join(cmd)} in {cwd}")
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                env=env,
                timeout=1800
            )
            
            if result.returncode != 0:
                logger.error(f"Terraform command failed: {result.stderr}")

            clean_stdout = ANSI_ESCAPE_RE.sub("", result.stdout or "")
            clean_stderr = ANSI_ESCAPE_RE.sub("", result.stderr or "")
            
            return {
                "success": result.returncode == 0,
                "stdout": clean_stdout,
                "stderr": clean_stderr,
                "error": clean_stderr if result.returncode != 0 else None,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            logger.error(f"Terraform command timed out: {' '.join(cmd)}")
            return {"success": False, "error": f"Terraform {cmd[1]} timed out"}
        except Exception as e:
            logger.error(f"Error running terraform: {str(e)}")
            return {"success": False, "error": str(e)}

    def init(self, project_dir: str) -> Dict[str, Any]:
        """Initialize Terraform in a project directory"""
        project_path = self.workspace_dir / project_dir
        project_path.mkdir(parents=True, exist_ok=True)
        return self._run_terraform(["terraform", "init"], project_path)
    
    def plan(self, project_dir: str, var_file: Optional[str] = None) -> Dict[str, Any]:
        """Run terraform plan"""
        project_path = self.workspace_dir / project_dir
        cmd = ["terraform", "plan", "-out=tfplan", "-input=false"]
        if var_file:
            cmd.extend(["-var-file", var_file])
        return self._run_terraform(cmd, project_path)
    
    def apply(self, project_dir: str, auto_approve: bool = False) -> Dict[str, Any]:
        """Run terraform apply"""
        project_path = self.workspace_dir / project_dir
        plan_file = project_path / "tfplan"
        
        # If we have a saved plan, use it
        if plan_file.exists():
            cmd = ["terraform", "apply", "-input=false", "tfplan"]
        elif auto_approve:
            cmd = ["terraform", "apply", "-auto-approve", "-input=false"]
        else:
            return {"success": False, "error": "No tfplan file found. Please run terraform_plan first."}
        
        return self._run_terraform(cmd, project_path)
    
    def destroy(self, project_dir: str, auto_approve: bool = True) -> Dict[str, Any]:
        """Run terraform destroy"""
        project_path = self.workspace_dir / project_dir
        
        # Check if project directory exists
        if not project_path.exists():
            logger.error(f"Project directory does not exist: {project_path}")
            return {
                "success": False,
                "error": f"Project directory '{project_dir}' not found. Use terraform_plan first to create the project."
            }
        
        # Remove any existing tfplan file to avoid conflicts
        plan_file = project_path / "tfplan"
        if plan_file.exists():
            try:
                plan_file.unlink()
                logger.info(f"Removed existing tfplan file before destroy: {plan_file}")
            except Exception as e:
                logger.warning(f"Could not remove tfplan file: {e}")
        
        # Build destroy command - always use auto_approve flag
        cmd = ["terraform", "destroy", "-input=false", "-auto-approve"]
        
        try:
            # Inherit current env and overlay with active session credentials
            env = os.environ.copy()
            if self.rbac:
                creds = self.rbac.get_credentials_env()
                env.update(creds)
                if "AWS_PROFILE" in env:
                    # Remove AWS_PROFILE to ensure injected credentials are used
                    del env["AWS_PROFILE"]
            
            logger.info(f"EXECUTION: Real AWS Destruction - Running command: {' '.join(cmd)} in {project_path}")
            result = subprocess.run(
                cmd,
                cwd=project_path,
                capture_output=True,
                text=True,
                env=env,
                timeout=1800
            )
            
            if result.returncode != 0:
                logger.error(f"Terraform destroy command failed: {result.stderr}")
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            logger.error(f"Terraform destroy timed out: {' '.join(cmd)}")
            return {"success": False, "error": "Terraform destroy timed out (exceeded 30 minutes)"}
        except Exception as e:
            logger.error(f"Error running terraform destroy: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def show_state(self, project_dir: str) -> Dict[str, Any]:
        """Show current Terraform state"""
        project_path = self.workspace_dir / project_dir
        
        try:
            result = subprocess.run(
                ["terraform", "show", "-json"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                try:
                    state = json.loads(result.stdout)
                    return {"success": True, "state": state}
                except json.JSONDecodeError:
                    return {"success": False, "error": "Failed to parse state JSON"}
            
            return {
                "success": False,
                "stderr": result.stderr
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Terraform show timed out"}


class AWSCLIManager:
    """Manages direct AWS CLI operations"""
    
    def __init__(self, rbac_manager=None):
        self.rbac = rbac_manager

    def _run_aws_cli(self, cmd: List[str]) -> Dict[str, Any]:
        """Run AWS CLI command with inherited environment and explicit credentials"""
        try:
            full_cmd = ["aws"] + cmd
            # Inherit env and overlay with session credentials
            env = os.environ.copy()
            if self.rbac:
                creds = self.rbac.get_credentials_env()
                env.update(creds)
                if "AWS_PROFILE" in env:
                    del env["AWS_PROFILE"]
            
            logger.info(f"EXECUTION: Real AWS Provisioning - Running AWS CLI: {' '.join(full_cmd)}")
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=600
            )
            
            if result.returncode != 0:
                logger.error(f"AWS CLI command failed: {result.stderr}")
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "error": result.stderr if result.returncode != 0 else None,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            logger.error(f"AWS CLI command timed out: {' '.join(full_cmd)}")
            return {"success": False, "error": "AWS CLI command timed out"}
        except Exception as e:
            logger.error(f"Error running AWS CLI: {str(e)}")
            return {"success": False, "error": str(e)}

    def create_s3_bucket(self, bucket_name: str, region: str = "us-east-1") -> Dict[str, Any]:
        """Create S3 bucket using AWS CLI"""
        cmd = ["s3api", "create-bucket", "--bucket", bucket_name, "--region", region]
        if region != "us-east-1":
            cmd.extend(["--create-bucket-configuration", f"LocationConstraint={region}"])
        return self._run_aws_cli(cmd)

    def create_ec2_instance(self, instance_type: str, ami_id: str, region: str) -> Dict[str, Any]:
        """Create EC2 instance using AWS CLI"""
        cmd = [
            "ec2", "run-instances",
            "--image-id", ami_id,
            "--count", "1",
            "--instance-type", instance_type,
            "--region", region,
            "--tag-specifications", f"ResourceType=instance,Tags=[{{Key=Name,Value=CLI-Provisioned-Instance}},{{Key=ManagedBy,Value=AWS-Infra-Agent-MCP}}]"
        ]
        return self._run_aws_cli(cmd)

    def create_vpc(self, cidr_block: str, region: str) -> Dict[str, Any]:
        """Create VPC using AWS CLI"""
        cmd = ["ec2", "create-vpc", "--cidr-block", cidr_block, "--region", region]
        return self._run_aws_cli(cmd)

    def create_lambda_function(self, function_name: str, role_arn: str, handler: str, runtime: str, zip_file: str, region: str) -> Dict[str, Any]:
        """Create Lambda function using AWS CLI"""
        cmd = [
            "lambda", "create-function",
            "--function-name", function_name,
            "--role", role_arn,
            "--handler", handler,
            "--runtime", runtime,
            "--zip-file", f"fileb://{zip_file}",
            "--region", region
        ]
        return self._run_aws_cli(cmd)


class AWSInfrastructureTemplates:
    """Pre-built Terraform templates for common AWS infrastructure"""
    
    @staticmethod
    def ec2_instance(instance_type: str = "t2.micro", ami_id: str = None, region: str = "us-east-1", security_group_id: str = None) -> str:
        """Generate Terraform config for EC2 instance
        
        Args:
            instance_type: EC2 instance type (default: t2.micro)
            ami_id: Optional AMI ID (if None, queries for latest Amazon Linux 2023)
            region: AWS region (default: us-east-1)
            security_group_id: Optional existing security group ID (if None, creates new one)
        """
        
        ami_block = ""
        actual_ami = f'"{ami_id}"' if ami_id else "data.aws_ami.amazon_linux_2023.id"
        
        if not ami_id:
            ami_block = """
data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023*-x86_64"]
  }
}
"""
        
        # Security group block: use existing or create new
        if security_group_id:
            sg_reference = f'"{security_group_id}"'
            sg_resource_block = f"""
# Using existing security group {security_group_id}
"""
        else:
            sg_reference = "aws_security_group.instance_sg.id"
            sg_resource_block = """
resource "aws_security_group" "instance_sg" {
  name        = "allow_ssh_http"
  description = "Allow SSH and HTTP traffic"

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
"""

        return f"""
terraform {{
  required_providers {{
    aws = {{
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }}
  }}
}}

provider "aws" {{
  region = "{region}"
}}

{ami_block}
{sg_resource_block}

resource "aws_instance" "main" {{
  ami           = {actual_ami}
  instance_type = "{instance_type}"
  vpc_security_group_ids = [{sg_reference}]
  
  tags = {{
    Name = "Production-Instance"
    ManagedBy = "AWS-Infra-Agent-MCP"
  }}
}}

output "instance_id" {{
  value = aws_instance.main.id
}}

output "public_ip" {{
  value = aws_instance.main.public_ip
}}
"""
    
    @staticmethod
    def s3_bucket(bucket_name: str, region: str = "us-east-1", versioning: bool = True) -> str:
        """Generate Terraform config for S3 bucket"""
        versioning_block = ""
        if versioning:
            versioning_block = f"""
resource "aws_s3_bucket_versioning" "main" {{
  bucket = aws_s3_bucket.main.id
  versioning_configuration {{
    status = "Enabled"
  }}
}}"""

        return f"""
terraform {{
  required_providers {{
    aws = {{
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }}
  }}
}}

provider "aws" {{
  region = "{region}"
}}

resource "aws_s3_bucket" "main" {{
  bucket = "{bucket_name}"
  
  tags = {{
    Name = "MCP-Provisioned-Bucket"
    ManagedBy = "AWS-Infra-Agent-MCP"
  }}
}}
{versioning_block}

output "bucket_name" {{
  value = aws_s3_bucket.main.id
}}

output "bucket_arn" {{
  value = aws_s3_bucket.main.arn
}}
"""
    
    @staticmethod
    def vpc_network(cidr_block: str = "10.0.0.0/16", region: str = "us-east-1") -> str:
        """Generate production-grade VPC config with public/private subnets across multiple AZs"""
        return f"""
terraform {{
  required_providers {{
    aws = {{
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }}
  }}
}}

provider "aws" {{
  region = "{region}"
}}

data "aws_availability_zones" "available" {{
  state = "available"
}}

resource "aws_vpc" "main" {{
  cidr_block           = "{cidr_block}"
  enable_dns_hostnames = true
  enable_dns_support   = true
  
  tags = {{
    Name = "Production-VPC"
    ManagedBy = "AWS-Infra-Agent-MCP"
  }}
}}

resource "aws_subnet" "public" {{
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index)
  availability_zone = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true
  
  tags = {{
    Name = "Public-Subnet-${{count.index + 1}}"
  }}
}}

resource "aws_subnet" "private" {{
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index + 2)
  availability_zone = data.aws_availability_zones.available.names[count.index]
  
  tags = {{
    Name = "Private-Subnet-${{count.index + 1}}"
  }}
}}

resource "aws_internet_gateway" "main" {{
  vpc_id = aws_vpc.main.id
  
  tags = {{
    Name = "Production-IGW"
  }}
}}

resource "aws_route_table" "public" {{
  vpc_id = aws_vpc.main.id
  
  route {{
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }}
}}

resource "aws_route_table_association" "public" {{
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}}

output "vpc_id" {{
  value = aws_vpc.main.id
}}

output "public_subnet_ids" {{
  value = aws_subnet.public[*].id
}}

output "private_subnet_ids" {{
  value = aws_subnet.private[*].id
}}
"""

    @staticmethod
    def rds_instance(db_name: str, instance_class: str = "db.t3.micro", region: str = "us-east-1") -> str:
        """Generate Terraform config for an RDS PostgreSQL instance"""
        return f"""
terraform {{
  required_providers {{
    aws = {{
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }}
  }}
}}

provider "aws" {{
  region = "{region}"
}}

resource "aws_db_instance" "default" {{
  allocated_storage    = 20
  db_name              = "{db_name}"
  engine               = "postgres"
  engine_version       = "15"
  instance_class       = "{instance_class}"
  username             = "adminuser"
  password             = "REPLACE_WITH_SECURE_PASSWORD" # Agent should advise user
  parameter_group_name = "default.postgres15"
  skip_final_snapshot  = true
  
  tags = {{
    Name = "Production-DB"
  }}
}}
"""

    @staticmethod
    def lambda_function(function_name: str, region: str = "us-east-1") -> str:
        """Generate Terraform config for a Lambda function"""
        return f"""
terraform {{
  required_providers {{
    aws = {{
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }}
  }}
}}

provider "aws" {{
  region = "{region}"
}}

resource "aws_iam_role" "iam_for_lambda" {{
  name = "iam_for_lambda_${{function_name}}"

  assume_role_policy = jsonencode({{
    Version = "2012-10-17"
    Statement = [
      {{
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Sid    = ""
        Principal = {{
          Service = "lambda.amazonaws.com"
        }}
      }},
    ]
  }})
}}

resource "aws_lambda_function" "test_lambda" {{
  filename      = "lambda_function_payload.zip"
  function_name = "{function_name}"
  role          = aws_iam_role.iam_for_lambda.arn
  handler       = "index.handler"

  runtime = "python3.9"

  environment {{
    variables = {{
      foo = "bar"
    }}
  }}
}}
"""

    @staticmethod
    def ecs_fargate_service(
        *,
        region: str,
        cluster_name: str,
        service_name: str,
        container_image: str,
        execution_role_arn: str,
        task_role_arn: str,
        subnet_ids: List[str],
        security_group_ids: List[str],
        container_port: int = 8080,
        desired_count: int = 1,
        cpu: int = 256,
        memory: int = 512,
        assign_public_ip: bool = True
    ) -> str:
        """Generate Terraform config for ECS Fargate service on an existing VPC/network."""
        subnets_hcl = ", ".join([f'"{s}"' for s in subnet_ids])
        sgs_hcl = ", ".join([f'"{s}"' for s in security_group_ids])
        assign_public_ip_hcl = "true" if assign_public_ip else "false"

        return f"""
terraform {{
  required_providers {{
    aws = {{
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }}
  }}
}}

provider "aws" {{
  region = "{region}"
}}

resource "aws_cloudwatch_log_group" "ecs_logs" {{
  name              = "/ecs/{service_name}"
  retention_in_days = 14

  tags = {{
    ManagedBy = "AWS-Infra-Agent-MCP"
  }}
}}

resource "aws_ecs_cluster" "main" {{
  name = "{cluster_name}"

  setting {{
    name  = "containerInsights"
    value = "enabled"
  }}

  tags = {{
    Name      = "{cluster_name}"
    ManagedBy = "AWS-Infra-Agent-MCP"
  }}
}}

resource "aws_ecs_task_definition" "app" {{
  family                   = "{service_name}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "{cpu}"
  memory                   = "{memory}"
  execution_role_arn       = "{execution_role_arn}"
  task_role_arn            = "{task_role_arn}"

  container_definitions = jsonencode([
    {{
      name      = "{service_name}"
      image     = "{container_image}"
      essential = true
      portMappings = [
        {{
          containerPort = {container_port}
          protocol      = "tcp"
        }}
      ]
      logConfiguration = {{
        logDriver = "awslogs"
        options = {{
          awslogs-group         = aws_cloudwatch_log_group.ecs_logs.name
          awslogs-region        = "{region}"
          awslogs-stream-prefix = "ecs"
        }}
      }}
    }}
  ])
}}

resource "aws_ecs_service" "app" {{
  name            = "{service_name}"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = {desired_count}
  launch_type     = "FARGATE"

  network_configuration {{
    subnets          = [{subnets_hcl}]
    security_groups  = [{sgs_hcl}]
    assign_public_ip = {assign_public_ip_hcl}
  }}

  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200

  tags = {{
    Name      = "{service_name}"
    ManagedBy = "AWS-Infra-Agent-MCP"
  }}
}}

output "ecs_cluster_name" {{
  value = aws_ecs_cluster.main.name
}}

output "ecs_service_name" {{
  value = aws_ecs_service.app.name
}}
"""


# MCP Server Tools
class MCPAWSManagerServer:
    """MCP Server for AWS provisioning via Terraform or CLI"""
    
    def __init__(self):
        self.rbac = AWSRBACManager()
        self.terraform = TerraformManager(rbac_manager=self.rbac)
        self.aws_cli = AWSCLIManager(rbac_manager=self.rbac)
        self.templates = AWSInfrastructureTemplates()
        self.ecs_workflows: Dict[str, Dict[str, Any]] = {}

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
            "message": "AWS Manager MCP Server initialized successfully. Tools support both 'terraform' and 'cli' modes via the 'mode' parameter.",
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
                "description": "Create an EC2 instance using Terraform or AWS CLI",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "instance_type": {
                            "type": "string", 
                            "description": "EC2 instance type (default: t2.micro)"
                        },
                        "region": {
                            "type": "string",
                            "description": "AWS region (default: us-east-1)"
                        },
                        "ami_id": {
                            "type": "string",
                            "description": "AMI ID (optional)"
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["terraform", "cli"],
                            "description": "Provisioning method (default: terraform)"
                        }
                    }
                }
            },
            {
                "name": "create_s3_bucket",
                "description": "Create an S3 bucket. Supports 'terraform' mode (default) for state management or 'cli' mode for direct execution.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "bucket_name": {
                            "type": "string",
                            "description": "S3 bucket name (required)"
                        },
                        "region": {
                            "type": "string",
                            "description": "AWS region (default: us-east-1)"
                        },
                        "versioning": {
                            "type": "boolean",
                            "description": "Enable versioning (default: true)"
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["terraform", "cli"],
                            "description": "Provisioning method (default: terraform)"
                        }
                    },
                    "required": ["bucket_name"]
                }
            },
            {
                "name": "create_vpc",
                "description": "Create a VPC with subnets using Terraform or AWS CLI",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "cidr_block": {
                            "type": "string",
                            "description": "VPC CIDR block (default: 10.0.0.0/16)"
                        },
                        "region": {
                            "type": "string",
                            "description": "AWS region (default: us-east-1)"
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["terraform", "cli"],
                            "description": "Provisioning method (default: terraform)"
                        }
                    }
                }
            },
            {
                "name": "create_rds_instance",
                "description": "Create an RDS PostgreSQL instance using Terraform or AWS CLI",
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
                            "description": "AWS region (default: us-east-1)"
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["terraform", "cli"],
                            "description": "Provisioning method (default: terraform)"
                        }
                    },
                    "required": ["db_name"]
                }
            },
            {
                "name": "create_lambda_function",
                "description": "Create a Lambda function using Terraform or AWS CLI",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "function_name": {
                            "type": "string",
                            "description": "Lambda function name (required)"
                        },
                        "region": {
                            "type": "string",
                            "description": "AWS region (default: us-east-1)"
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["terraform", "cli"],
                            "description": "Provisioning method (default: terraform)"
                        }
                    },
                    "required": ["function_name"]
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
            "list_aws_resources": self._list_aws_resources,
            "describe_resource": self._describe_resource,
            "list_account_inventory": self._list_account_inventory
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

    def _start_ecs_deployment_workflow(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Start a multi-turn ECS deployment workflow."""
        workflow_id = f"ecs-{uuid.uuid4().hex[:12]}"
        config = {
            "region": params.get("region") or os.getenv("AWS_REGION") or "us-east-1",
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
                "region": params.get("region") or os.getenv("AWS_REGION") or "us-east-1",
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
                "missing_fields": missing
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
        """Create RDS instance using Terraform or CLI"""
        db_name = params.get("db_name")
        instance_class = params.get("instance_class", "db.t3.micro")
        region = params.get("region", "us-east-1")
        mode = params.get("mode", "terraform").lower() or "terraform"
        
        if mode == "cli":
            # Direct CLI provisioning
            return {
                "success": False,
                "error": "RDS CLI provisioning is complex and not yet implemented for direct CLI mode. Please use 'terraform' mode for RDS."
            }
            
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
        """Create Lambda function using Terraform or CLI"""
        function_name = params.get("function_name")
        region = params.get("region", "us-east-1")
        mode = params.get("mode", "terraform").lower() or "terraform"
        
        if mode == "cli":
            return {
                "success": False,
                "error": "Lambda CLI provisioning requires pre-existing IAM roles and zip files. Please use 'terraform' mode for zero-config Lambda deployment."
            }

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
        """Create EC2 instance using Terraform or CLI"""
        instance_type = params.get("instance_type", "t2.micro")
        region = params.get("region", "us-east-1")
        ami_id = params.get("ami_id")
        mode = params.get("mode", "terraform").lower() or "terraform"
        
        # Check permissions
        if not self.rbac.check_permission("ec2:RunInstances"):
            return {"success": False, "error": "User lacks ec2:RunInstances permission"}
        
        if mode == "cli":
            if not ami_id:
                return {"success": False, "error": "ami_id is required for CLI mode"}
            return self.aws_cli.create_ec2_instance(instance_type, ami_id, region)

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
        """Create S3 bucket using Terraform or CLI"""
        bucket_name = params.get("bucket_name")
        if not bucket_name:
            return {"success": False, "error": "bucket_name is required"}
        
        region = params.get("region", "us-east-1")
        versioning = params.get("versioning", True)
        mode = params.get("mode", "terraform").lower() or "terraform"
        
        # Check permissions
        if not self.rbac.check_permission("s3:CreateBucket"):
            return {"success": False, "error": "User lacks s3:CreateBucket permission"}
        
        if mode == "cli":
            return self.aws_cli.create_s3_bucket(bucket_name, region)

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
        """Create VPC using Terraform or CLI"""
        cidr_block = params.get("cidr_block", "10.0.0.0/16")
        region = params.get("region", "us-east-1")
        mode = params.get("mode", "terraform").lower() or "terraform"
        
        # Check permissions
        if not self.rbac.check_permission("ec2:CreateVpc"):
            return {"success": False, "error": "User lacks ec2:CreateVpc permission"}
        
        if mode == "cli":
            return self.aws_cli.create_vpc(cidr_block, region)

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
