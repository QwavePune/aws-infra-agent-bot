"""Terraform execution helpers for MCP server."""

import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

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
            available = self._projects_with_tfplan()
            if available:
                return {
                    "success": False,
                    "error": (
                        f"No tfplan file found for project '{project_dir}'. "
                        f"Run terraform_plan first. Projects with an existing tfplan: {', '.join(available)}."
                    ),
                }
            return {"success": False, "error": "No tfplan file found. Please run terraform_plan first."}

        result = self._run_terraform(cmd, project_path)
        if not result.get("success"):
            stderr = result.get("stderr", "") or ""
            if "VPCIdNotSpecified" in stderr:
                hint = (
                    "No default VPC exists in this account/region. "
                    "Create a VPC first (for example with create_vpc + terraform_apply) "
                    "or update the EC2 Terraform to use an explicit VPC/subnet/security group."
                )
                result["hint"] = hint
                if result.get("error"):
                    result["error"] = f"{result['error']}\n\nHint: {hint}"
                else:
                    result["error"] = hint
        return result
    
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

    def _projects_with_tfplan(self) -> List[str]:
        """List workspace projects that currently have a saved tfplan file."""
        projects: List[str] = []
        if not self.workspace_dir.exists():
            return projects
        for project_path in self.workspace_dir.iterdir():
            if project_path.is_dir() and (project_path / "tfplan").exists():
                projects.append(project_path.name)
        projects.sort()
        return projects

