#!/usr/bin/env python3
"""
Example: Using Architecture-Driven Deployment

This script demonstrates how to use the architecture parsing and deployment features.
"""

import requests
import json

# AGUI Server URL
AGUI_URL = "http://localhost:9595"

# Example 1: Parse a Mermaid diagram
def example_parse_mermaid():
    print("=" * 60)
    print("Example 1: Parse Mermaid Diagram")
    print("=" * 60)
    
    mermaid_content = """
    graph LR
        VPC["AWS VPC"]
        EC2["EC2 t3.micro"]
        S3["S3 Bucket"]
        RDS["RDS MySQL"]
        
        VPC --> EC2
        VPC --> RDS
        EC2 --> S3
    """
    
    payload = {"mermaid": mermaid_content}
    response = requests.post(
        f"{AGUI_URL}/api/architecture/parse-mermaid",
        json=payload
    )
    
    result = response.json()
    print(json.dumps(result, indent=2))
    return result


# Example 2: Generate Terraform from parsed architecture
def example_generate_terraform(architecture):
    print("\n" + "=" * 60)
    print("Example 2: Generate Terraform from Architecture")
    print("=" * 60)
    
    payload = {"architecture": architecture}
    response = requests.post(
        f"{AGUI_URL}/api/architecture/generate-terraform",
        json=payload,
        params={"provider": "claude"}
    )
    
    result = response.json()
    print("Project Name:", result.get("project_name"))
    print("\nTerraform Code Preview:")
    print(result.get("terraform_code", "")[:500] + "...")
    return result


# Example 3: Deploy architecture (one-shot)
def example_deploy_architecture(architecture):
    print("\n" + "=" * 60)
    print("Example 3: Deploy Architecture (Generate + Plan)")
    print("=" * 60)
    
    payload = {"architecture": architecture}
    response = requests.post(
        f"{AGUI_URL}/api/architecture/deploy",
        json=payload,
        params={"provider": "claude"}
    )
    
    result = response.json()
    print("Success:", result.get("success"))
    print("Project Name:", result.get("project_name"))
    print("Message:", result.get("message"))
    print("\nPlan Result:")
    print(json.dumps(result.get("plan_result", {}), indent=2)[:300])
    return result


# Example 4: Parse architecture image
def example_parse_image(image_path):
    print("\n" + "=" * 60)
    print("Example 4: Parse Architecture Image")
    print("=" * 60)
    
    with open(image_path, "rb") as f:
        files = {"file": f}
        response = requests.post(
            f"{AGUI_URL}/api/architecture/parse-image",
            files=files,
            params={"provider": "claude"}
        )
    
    result = response.json()
    print(json.dumps(result, indent=2))
    return result


# Example 5: Full workflow with MCP server
def example_mcp_workflow():
    print("\n" + "=" * 60)
    print("Example 5: Full Workflow with MCP Server")
    print("=" * 60)
    
    # This would be used when the agent is calling MCP tools directly
    # The MCP server provides: parse_mermaid_architecture, generate_terraform_from_architecture, deploy_architecture
    
    print("""
    When using MCP server directly:
    
    1. Agent calls: parse_mermaid_architecture
       Input: mermaid_content
       Output: architecture dict
    
    2. Agent calls: generate_terraform_from_architecture
       Input: architecture dict
       Output: terraform_code, project_name
    
    3. Agent calls: deploy_architecture
       Input: architecture dict
       Output: project ready for terraform_apply
    """)


# Complex example: Multi-tier application
def example_multi_tier_app():
    print("\n" + "=" * 60)
    print("Example 6: Multi-Tier Application")
    print("=" * 60)
    
    mermaid_content = """
    graph TB
        Users["End Users"]
        CloudFront["CloudFront CDN"]
        ALB["Application Load Balancer"]
        
        subgraph PrivateSubnet["Private Subnet"]
            Web1["Web Server 1"]
            Web2["Web Server 2"]
            API1["API Server 1"]
            API2["API Server 2"]
        end
        
        subgraph Database["Database Layer"]
            RDS["RDS MySQL Master"]
            RDSRead["RDS MySQL Read Replica"]
        end
        
        Cache["ElastiCache Redis"]
        S3["S3 Static Assets"]
        CloudWatch["CloudWatch Monitoring"]
        
        Users --> CloudFront
        CloudFront --> S3
        CloudFront --> ALB
        ALB --> Web1
        ALB --> Web2
        Web1 --> API1
        Web2 --> API2
        API1 --> RDS
        API2 --> RDS
        RDS --> RDSRead
        API1 --> Cache
        API2 --> Cache
        Web1 -.-> CloudWatch
        Web2 -.-> CloudWatch
        API1 -.-> CloudWatch
        API2 -.-> CloudWatch
    """
    
    payload = {"mermaid": mermaid_content}
    response = requests.post(
        f"{AGUI_URL}/api/architecture/parse-mermaid",
        json=payload
    )
    
    architecture = response.json()
    print(f"Extracted {len(architecture.get('resources', []))} resources")
    print(f"Found {len(architecture.get('relationships', []))} relationships")
    
    # Now generate Terraform
    gen_response = requests.post(
        f"{AGUI_URL}/api/architecture/generate-terraform",
        json={"architecture": architecture},
        params={"provider": "claude"}
    )
    
    gen_result = gen_response.json()
    print(f"Generated Terraform project: {gen_result.get('project_name')}")
    print(f"Terraform code size: {len(gen_result.get('terraform_code', ''))} bytes")


if __name__ == "__main__":
    print("\nArchitecture-Driven Deployment Examples\n")
    
    # Run examples
    try:
        # Example 1: Parse Mermaid
        arch = example_parse_mermaid()
        
        # Example 2: Generate Terraform
        # example_generate_terraform(arch)
        
        # Example 3: Deploy (commented to avoid actual deployment)
        # example_deploy_architecture(arch)
        
        # Example 4: Parse Image (requires image file)
        # example_parse_image("/path/to/architecture.png")
        
        # Example 5: MCP workflow info
        example_mcp_workflow()
        
        # Example 6: Multi-tier app
        # example_multi_tier_app()
        
    except requests.exceptions.ConnectionError:
        print("ERROR: Could not connect to AGUI server at", AGUI_URL)
        print("Make sure the server is running: python bin/agui_server.py")
    except Exception as e:
        print(f"ERROR: {e}")
