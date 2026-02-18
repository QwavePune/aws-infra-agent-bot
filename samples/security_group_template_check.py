#!/usr/bin/env python3
"""Test security group reuse logic"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from mcp_servers.aws_terraform_server import AWSInfrastructureTemplates

# Test 1: Create new security group
print("Test 1: Generate config WITHOUT existing security group")
config1 = AWSInfrastructureTemplates.ec2_instance(
    instance_type='t3.micro',
    ami_id=None,
    region='ap-south-1',
    security_group_id=None
)
has_sg_resource = 'resource "aws_security_group"' in config1
has_data_ami = 'data "aws_ami"' in config1
print(f"  Creates security group resource: {has_sg_resource} ✅" if has_sg_resource else f"  Creates security group resource: {has_sg_resource} ❌")
print(f"  Has dynamic AMI lookup: {has_data_ami} ✅" if has_data_ami else f"  Has dynamic AMI lookup: {has_data_ami} ❌")

# Test 2: Reuse existing security group
print("\nTest 2: Generate config WITH existing security group (sg-12345678)")
config2 = AWSInfrastructureTemplates.ec2_instance(
    instance_type='t3.micro',
    ami_id=None,
    region='ap-south-1',
    security_group_id='sg-12345678'
)
no_sg_resource = 'resource "aws_security_group"' not in config2
has_sg_ref = '"sg-12345678"' in config2
print(f"  Does NOT create security group resource: {no_sg_resource} ✅" if no_sg_resource else f"  Does NOT create security group resource: {no_sg_resource} ❌")
print(f"  References sg-12345678: {has_sg_ref} ✅" if has_sg_ref else f"  References sg-12345678: {has_sg_ref} ❌")

# Show the resource block that uses the SG
print("\n  EC2 Instance resource block:")
for line in config2.split('\n'):
    if 'resource "aws_instance"' in line or 'vpc_security_group_ids' in line:
        print(f"    {line}")

print("\n✅ All tests passed!" if all([has_sg_resource, has_data_ami, no_sg_resource, has_sg_ref]) else "\n❌ Some tests failed!")
