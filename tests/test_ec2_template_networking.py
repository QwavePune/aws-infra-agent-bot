"""Unit tests for EC2 template networking defaults."""

from mcp_servers.aws_terraform.templates import AWSInfrastructureTemplates


def test_ec2_template_uses_explicit_subnet_and_vpc_for_new_security_group():
    config = AWSInfrastructureTemplates.ec2_instance(
        instance_type="t3.micro",
        region="ap-south-1",
        security_group_id=None,
    )

    assert 'data "aws_subnets" "available"' in config
    assert 'data "aws_subnet" "selected"' in config
    assert "subnet_id     = data.aws_subnet.selected.id" in config
    assert "vpc_id      = data.aws_subnet.selected.vpc_id" in config
