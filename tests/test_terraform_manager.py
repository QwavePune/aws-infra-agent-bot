"""Unit tests for Terraform manager apply guardrails."""

from mcp_servers.aws_terraform.terraform import TerraformManager


def test_apply_reports_projects_with_existing_tfplan(tmp_path):
    manager = TerraformManager(workspace_dir=str(tmp_path))
    (tmp_path / "planned_project").mkdir(parents=True, exist_ok=True)
    (tmp_path / "planned_project" / "tfplan").write_text("fake-plan")
    (tmp_path / "unplanned_project").mkdir(parents=True, exist_ok=True)

    result = manager.apply("unplanned_project", auto_approve=False)

    assert result["success"] is False
    assert "No tfplan file found for project 'unplanned_project'" in result["error"]
    assert "planned_project" in result["error"]


def test_apply_adds_hint_for_missing_default_vpc(tmp_path):
    manager = TerraformManager(workspace_dir=str(tmp_path))
    (tmp_path / "ec2_project").mkdir(parents=True, exist_ok=True)
    (tmp_path / "ec2_project" / "tfplan").write_text("fake-plan")

    def _fake_run(_cmd, _cwd):
        return {
            "success": False,
            "stdout": "aws_security_group.instance_sg: Creating...\n",
            "stderr": "api error VPCIdNotSpecified: No default VPC for this user",
            "error": "api error VPCIdNotSpecified: No default VPC for this user",
            "returncode": 1,
        }

    manager._run_terraform = _fake_run  # type: ignore[method-assign]
    result = manager.apply("ec2_project", auto_approve=False)

    assert result["success"] is False
    assert "VPCIdNotSpecified" in result["error"]
    assert "Hint:" in result["error"]
    assert "create_vpc" in result["error"]
