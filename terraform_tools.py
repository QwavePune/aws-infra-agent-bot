import subprocess
import os
import json
from typing import Optional
from langchain_core.tools import Tool

class TerraformTool:
    """A tool for running Terraform commands."""

    def __init__(self, base_dir: str = "."):
        self.base_dir = base_dir

    def _run_command(self, command: list[str], cwd: Optional[str] = None) -> str:
        """Run a shell command and return the output."""
        full_cwd = os.path.join(self.base_dir, cwd) if cwd else self.base_dir
        if not os.path.exists(full_cwd):
            os.makedirs(full_cwd, exist_ok=True)

        try:
            result = subprocess.run(
                command,
                cwd=full_cwd,
                capture_output=True,
                text=True,
                check=False
            )
            output = result.stdout
            if result.stderr:
                output += "\nErrors:\n" + result.stderr
            return output
        except Exception as e:
            return f"Exception occurred: {str(e)}"

    def init(self, directory: str = ".") -> str:
        """Run terraform init."""
        return self._run_command(["terraform", "init"], cwd=directory)

    def plan(self, directory: str = ".") -> str:
        """Run terraform plan."""
        return self._run_command(["terraform", "plan"], cwd=directory)

    def apply(self, directory: str = ".") -> str:
        """Run terraform apply -auto-approve."""
        return self._run_command(["terraform", "apply", "-auto-approve"], cwd=directory)

    def destroy(self, directory: str = ".") -> str:
        """Run terraform destroy -auto-approve."""
        return self._run_command(["terraform", "destroy", "-auto-approve"], cwd=directory)

    def output(self, directory: str = ".") -> str:
        """Run terraform output."""
        return self._run_command(["terraform", "output"], cwd=directory)

    def write_file(self, filename: str, content: str, directory: str = ".") -> str:
        """Write a file (e.g. main.tf) to the specified directory."""
        full_dir = os.path.join(self.base_dir, directory)
        if not os.path.exists(full_dir):
            os.makedirs(full_dir, exist_ok=True)

        filepath = os.path.join(full_dir, filename)
        try:
            with open(filepath, "w") as f:
                f.write(content)
            return f"Successfully wrote {filename} to {directory}"
        except Exception as e:
            return f"Error writing file: {str(e)}"

def get_terraform_tools(base_dir: str = "terraform_data"):
    tf = TerraformTool(base_dir=base_dir)

    return [
        Tool(
            name="terraform_init",
            func=tf.init,
            description="Run terraform init in a directory. Useful to initialize a new terraform configuration."
        ),
        Tool(
            name="terraform_plan",
            func=tf.plan,
            description="Run terraform plan in a directory. Shows what changes will be made."
        ),
        Tool(
            name="terraform_apply",
            func=tf.apply,
            description="Run terraform apply in a directory. Deploys the infrastructure. Use with caution."
        ),
        Tool(
            name="terraform_destroy",
            func=tf.destroy,
            description="Run terraform destroy in a directory. Destroys the infrastructure."
        ),
        Tool(
            name="terraform_output",
            func=tf.output,
            description="Run terraform output in a directory. Shows the outputs of the deployment."
        ),
        Tool(
            name="write_terraform_file",
            func=lambda q: tf.write_file(**json.loads(q)) if q.strip().startswith("{") else "Error: input must be a JSON string like {\"filename\": \"main.tf\", \"content\": \"...\", \"directory\": \".\"}",
            description="Write a terraform file. Input should be a JSON string with keys: filename, content, directory (optional)."
        )
    ]
