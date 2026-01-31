from mcp.server.fastmcp import FastMCP
from terraform_tools import TerraformTool
import os

# Initialize FastMCP server
mcp = FastMCP("Terraform-AWS-Agent")

# Initialize TerraformTool
# We'll use a dedicated directory for terraform files
tf = TerraformTool(base_dir="terraform_deployments")

@mcp.tool()
def terraform_init(directory: str = ".") -> str:
    """Run terraform init in the specified directory."""
    return tf.init(directory)

@mcp.tool()
def terraform_plan(directory: str = ".") -> str:
    """Run terraform plan in the specified directory."""
    return tf.plan(directory)

@mcp.tool()
def terraform_apply(directory: str = ".") -> str:
    """Run terraform apply in the specified directory. This deploys infrastructure."""
    return tf.apply(directory)

@mcp.tool()
def terraform_destroy(directory: str = ".") -> str:
    """Run terraform destroy in the specified directory. This removes infrastructure."""
    return tf.destroy(directory)

@mcp.tool()
def terraform_output(directory: str = ".") -> str:
    """Get the terraform outputs for a deployment."""
    return tf.output(directory)

@mcp.tool()
def write_terraform_file(filename: str, content: str, directory: str = ".") -> str:
    """Write a terraform (.tf) file to a directory."""
    return tf.write_file(filename, content, directory)

if __name__ == "__main__":
    mcp.run()
