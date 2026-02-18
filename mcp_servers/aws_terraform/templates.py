"""Terraform template builders for common AWS infra patterns."""

from typing import List


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

        # Use an existing subnet in-region so EC2/SG creation does not depend on a default VPC.
        network_block = """
data "aws_subnets" "available" {}

data "aws_subnet" "selected" {
  id = tolist(data.aws_subnets.available.ids)[0]
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
  vpc_id      = data.aws_subnet.selected.vpc_id

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
{network_block}
{sg_resource_block}

resource "aws_instance" "main" {{
  ami           = {actual_ami}
  instance_type = "{instance_type}"
  subnet_id     = data.aws_subnet.selected.id
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
