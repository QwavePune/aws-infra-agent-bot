"""
AWS Terraform MCP Server

This MCP server provides tools for provisioning AWS infrastructure using Terraform.
It includes RBAC based on AWS IAM credentials and supports various infrastructure operations.
"""

import json
import os
import subprocess
import logging
from typing import Any, Dict, List, Optional
from pathlib import Path
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
            
            logger.info(f"AWS Identity Successfully Retreived: {self.identity.get('Arn')}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize AWS clients: {str(e)}")
            self.identity = None
            return False
    
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
            # Default to allowing if check fails (can be made stricter)
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


class TerraformManager:
    """Manages Terraform operations"""
    
    def __init__(self, workspace_dir: str = "./terraform_workspace"):
        self.workspace_dir = Path(workspace_dir)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        
    def _run_terraform(self, cmd: List[str], cwd: Path) -> Dict[str, Any]:
        """Run terraform command with inherited environment"""
        try:
            # Ensure AWS credentials from the current process are passed to terraform
            env = os.environ.copy()
            
            logger.info(f"Running command: {' '.join(cmd)} in {cwd}")
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
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
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
    
    def destroy(self, project_dir: str, auto_approve: bool = False) -> Dict[str, Any]:
        """Run terraform destroy"""
        project_path = self.workspace_dir / project_dir
        
        cmd = ["terraform", "destroy"]
        if auto_approve:
            cmd.append("-auto-approve")
        
        try:
            result = subprocess.run(
                cmd,
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=1800
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Terraform destroy timed out"}
    
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


class AWSInfrastructureTemplates:
    """Pre-built Terraform templates for common AWS infrastructure"""
    
    @staticmethod
    def ec2_instance(instance_type: str = "t2.micro", ami_id: str = None, region: str = "us-east-1") -> str:
        """Generate Terraform config for EC2 instance"""
        if not ami_id:
            # Default Amazon Linux 2 AMI (region-specific)
            ami_map = {
                "us-east-1": "ami-0c55b159cbfafe1f0",
                "us-west-2": "ami-0d1cd67c26f5fca19"
            }
            ami_id = ami_map.get(region, ami_map["us-east-1"])
        
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

resource "aws_security_group" "instance_sg" {{
  name        = "allow_ssh_http"
  description = "Allow SSH and HTTP traffic"

  ingress {{
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }}

  ingress {{
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }}

  egress {{
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }}
}}

resource "aws_instance" "main" {{
  ami           = "{ami_id}"
  instance_type = "{instance_type}"
  vpc_security_group_ids = [aws_security_group.instance_sg.id]
  
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


# MCP Server Tools
class MCPAWSTerraformServer:
    """MCP Server for AWS Terraform operations"""
    
    def __init__(self):
        self.rbac = AWSRBACManager()
        self.terraform = TerraformManager()
        self.templates = AWSInfrastructureTemplates()
        
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
            "message": "AWS Terraform MCP Server initialized successfully"
        }
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """List available MCP tools"""
        return [
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
                            "description": "AWS region (default: us-east-1)"
                        },
                        "ami_id": {
                            "type": "string",
                            "description": "AMI ID (optional)"
                        }
                    }
                }
            },
            {
                "name": "create_s3_bucket",
                "description": "Create an S3 bucket using Terraform",
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
                        }
                    },
                    "required": ["bucket_name"]
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
                            "description": "AWS region (default: us-east-1)"
                        }
                    }
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
                            "description": "AWS region (default: us-east-1)"
                        }
                    },
                    "required": ["db_name"]
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
                            "description": "AWS region (default: us-east-1)"
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
            }
        ]
    
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
            "create_ec2_instance": self._create_ec2_instance,
            "create_s3_bucket": self._create_s3_bucket,
            "create_vpc": self._create_vpc,
            "create_rds_instance": self._create_rds_instance,
            "create_lambda_function": self._create_lambda_function,
            "terraform_plan": self._terraform_plan,
            "terraform_apply": self._terraform_apply,
            "terraform_destroy": self._terraform_destroy,
            "get_infrastructure_state": self._get_infrastructure_state,
            "get_user_permissions": self._get_user_permissions
        }
        
        handler = handlers.get(tool_name)
        if not handler:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        
        return handler(parameters)

    def _create_rds_instance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create RDS instance"""
        db_name = params.get("db_name")
        instance_class = params.get("instance_class", "db.t3.micro")
        region = params.get("region", "us-east-1")
        
        # Generate Terraform config
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
        """Create Lambda function"""
        function_name = params.get("function_name")
        region = params.get("region", "us-east-1")
        
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
        """Create EC2 instance"""
        instance_type = params.get("instance_type", "t2.micro")
        region = params.get("region", "us-east-1")
        ami_id = params.get("ami_id")
        
        # Check permissions
        if not self.rbac.check_permission("ec2:RunInstances"):
            return {"success": False, "error": "User lacks ec2:RunInstances permission"}
        
        # Generate Terraform config
        project_name = f"ec2_{instance_type}_{region}"
        project_path = self.terraform.workspace_dir / project_name
        project_path.mkdir(parents=True, exist_ok=True)
        
        config = self.templates.ec2_instance(instance_type, ami_id, region)
        (project_path / "main.tf").write_text(config)
        
        # Initialize Terraform
        init_result = self.terraform.init(project_name)
        if not init_result["success"]:
            return init_result
        
        return {
            "success": True,
            "project_name": project_name,
            "message": f"EC2 instance project created. Run terraform_plan with project_name='{project_name}' to continue.",
            "config_preview": config[:500] + "..."
        }
    
    def _create_s3_bucket(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create S3 bucket"""
        bucket_name = params.get("bucket_name")
        if not bucket_name:
            return {"success": False, "error": "bucket_name is required"}
        
        region = params.get("region", "us-east-1")
        versioning = params.get("versioning", True)
        
        # Check permissions
        if not self.rbac.check_permission("s3:CreateBucket"):
            return {"success": False, "error": "User lacks s3:CreateBucket permission"}
        
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
            "config_preview": config[:500] + "..."
        }
    
    def _create_vpc(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create VPC"""
        cidr_block = params.get("cidr_block", "10.0.0.0/16")
        region = params.get("region", "us-east-1")
        
        # Check permissions
        if not self.rbac.check_permission("ec2:CreateVpc"):
            return {"success": False, "error": "User lacks ec2:CreateVpc permission"}
        
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
            "config_preview": config[:500] + "..."
        }
    
    def _terraform_plan(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Run terraform plan"""
        project_name = params.get("project_name")
        if not project_name:
            return {"success": False, "error": "project_name is required"}
        
        return self.terraform.plan(project_name)
    
    def _terraform_apply(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Run terraform apply"""
        project_name = params.get("project_name")
        if not project_name:
            return {"success": False, "error": "project_name is required"}
        
        auto_approve = params.get("auto_approve", False)
        return self.terraform.apply(project_name, auto_approve)
    
    def _terraform_destroy(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Run terraform destroy"""
        project_name = params.get("project_name")
        if not project_name:
            return {"success": False, "error": "project_name is required"}
        
        auto_approve = params.get("auto_approve", False)
        return self.terraform.destroy(project_name, auto_approve)
    
    def _get_infrastructure_state(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get infrastructure state"""
        project_name = params.get("project_name")
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


# Singleton instance
mcp_server = MCPAWSTerraformServer()
