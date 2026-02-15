"""
Architecture Parser Module

Parses AWS architecture images (vision-based) or Mermaid diagrams
and converts them to Terraform infrastructure code.
"""

import base64
import json
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path
import re

logger = logging.getLogger(__name__)


class ArchitectureParser:
    """Parse AWS architecture diagrams and generate Terraform code"""
    
    def __init__(self, llm_provider=None, llm_instance=None):
        """
        Initialize the parser with an LLM provider for vision capabilities
        
        Args:
            llm_provider: Name of LLM provider (e.g., 'claude', 'openai', 'gemini')
            llm_instance: Initialized LLM instance with vision capabilities
        """
        self.llm_provider = llm_provider
        self.llm = llm_instance
    
    def parse_mermaid_diagram(self, mermaid_content: str) -> Dict[str, Any]:
        """
        Parse a Mermaid diagram to extract AWS resources and architecture
        
        Args:
            mermaid_content: Mermaid diagram syntax (text)
        
        Returns:
            Dict containing identified resources and relationships
        """
        logger.info("Parsing Mermaid diagram")
        
        # Extract resources from Mermaid syntax
        resources = self._extract_mermaid_resources(mermaid_content)
        relationships = self._extract_mermaid_relationships(mermaid_content)
        
        return {
            "type": "mermaid",
            "resources": resources,
            "relationships": relationships,
            "raw": mermaid_content
        }
    
    def parse_architecture_image(self, image_path: str) -> Dict[str, Any]:
        """
        Parse an AWS architecture image using vision capabilities
        
        Args:
            image_path: Path to the architecture image file
        
        Returns:
            Dict containing identified resources and relationships
        """
        if not self.llm:
            return {
                "success": False,
                "error": "No LLM instance available for vision analysis. Please initialize with an LLM provider."
            }
        
        logger.info(f"Parsing architecture image: {image_path}")
        
        # Read and encode the image
        with open(image_path, "rb") as image_file:
            image_data = base64.standard_b64encode(image_file.read()).decode("utf-8")
        
        # Determine image type
        file_ext = Path(image_path).suffix.lower()
        media_type_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp"
        }
        media_type = media_type_map.get(file_ext, "image/png")
        
        # Use LLM vision to analyze the image
        try:
            from langchain_core.messages import HumanMessage
            
            analysis_prompt = """Analyze this AWS architecture diagram and extract:
1. All AWS services/resources (e.g., EC2, S3, RDS, Lambda, VPC, Load Balancer, etc.)
2. Their configurations (instance types, storage size, etc.)
3. Relationships between components (connections, data flow)
4. Network topology (VPCs, subnets, security groups)

Return the analysis as a JSON object with this structure:
{
    "resources": [
        {"type": "ec2", "name": "...", "details": {...}},
        {"type": "s3", "name": "...", "details": {...}},
        ...
    ],
    "relationships": [
        {"from": "...", "to": "...", "type": "connection_type"},
        ...
    ],
    "network": {
        "vpcs": [...],
        "subnets": [...],
        "security_groups": [...]
    },
    "description": "Brief description of the architecture"
}

Only return valid JSON, no markdown code blocks."""
            
            message = HumanMessage(
                content=[
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{image_data}"
                        }
                    },
                    {
                        "type": "text",
                        "text": analysis_prompt
                    }
                ]
            )
            
            response = self.llm.invoke([message])
            response_text = response.content
            
            # Parse the JSON response
            try:
                analysis = json.loads(response_text)
                return {
                    "success": True,
                    "type": "image",
                    "resources": analysis.get("resources", []),
                    "relationships": analysis.get("relationships", []),
                    "network": analysis.get("network", {}),
                    "description": analysis.get("description", ""),
                    "raw": response_text
                }
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM response as JSON: {e}")
                return {
                    "success": False,
                    "error": f"Invalid JSON response from vision analysis: {str(e)}",
                    "raw_response": response_text
                }
        
        except Exception as e:
            logger.error(f"Error analyzing architecture image: {e}")
            return {
                "success": False,
                "error": f"Failed to analyze image: {str(e)}"
            }
    
    def architecture_to_terraform(self, architecture: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert parsed architecture to Terraform configuration
        
        Args:
            architecture: Parsed architecture dict from parse_mermaid_diagram or parse_architecture_image
        
        Returns:
            Dict with terraform code and project structure
        """
        if not self.llm:
            return {
                "success": False,
                "error": "No LLM instance available. Please initialize with an LLM provider."
            }
        
        logger.info("Generating Terraform from architecture")
        
        # Prepare architecture description for Terraform generation
        arch_json = json.dumps(architecture, indent=2)
        
        try:
            from langchain_core.messages import HumanMessage
            
            terraform_prompt = f"""Based on this AWS architecture, generate Terraform code to provision the infrastructure.

Architecture:
{arch_json}

Requirements:
1. Generate complete, production-ready Terraform code
2. Use AWS provider version ~> 5.0
3. Include all necessary resources (VPCs, subnets, security groups, instances, databases, etc.)
4. Use data sources for AMIs
5. Include variables for configurable parameters
6. Include outputs for important resource attributes
7. Organize in a single main.tf file
8. Include comments explaining each resource
9. Use best practices (e.g., security groups for access control, encryption where applicable)

Return ONLY valid Terraform code, no markdown, no explanations, no code blocks."""
            
            message = HumanMessage(content=terraform_prompt)
            response = self.llm.invoke([message])
            terraform_code = response.content.strip()
            
            # Remove markdown code blocks if present
            if terraform_code.startswith("```"):
                terraform_code = re.sub(r'^```(?:hcl|terraform)?\n?', '', terraform_code)
                terraform_code = re.sub(r'\n?```$', '', terraform_code)
            
            # Extract project name from architecture
            project_name = self._extract_project_name(architecture)
            
            return {
                "success": True,
                "project_name": project_name,
                "terraform_code": terraform_code,
                "architecture": architecture,
                "message": f"Terraform code generated for project: {project_name}"
            }
        
        except Exception as e:
            logger.error(f"Error generating Terraform: {e}")
            return {
                "success": False,
                "error": f"Failed to generate Terraform code: {str(e)}"
            }
    
    def _extract_mermaid_resources(self, mermaid_content: str) -> List[Dict[str, Any]]:
        """Extract resources from Mermaid diagram"""
        resources = []
        
        # Simple pattern matching for Mermaid nodes
        # Supports patterns like: node_id["Label"]
        pattern = r'(\w+)\["?([^"\]]+)"?\]'
        matches = re.findall(pattern, mermaid_content)
        
        service_keywords = {
            'ec2': 'ec2', 'instance': 'ec2',
            's3': 's3', 'bucket': 's3',
            'rds': 'rds', 'database': 'rds',
            'dynamodb': 'dynamodb', 'table': 'dynamodb',
            'lambda': 'lambda', 'function': 'lambda',
            'vpc': 'vpc', 'subnet': 'vpc',
            'elb': 'load_balancer', 'alb': 'load_balancer',
            'apigateway': 'api_gateway',
            'sqs': 'sqs', 'sns': 'sns',
            'kinesis': 'kinesis',
            'cloudfront': 'cloudfront',
            'acm': 'certificate',
            'iam': 'iam', 'role': 'iam',
            'cloudwatch': 'cloudwatch',
            'autoscaling': 'autoscaling'
        }
        
        for node_id, label in matches:
            # Detect service type from label
            service_type = 'unknown'
            for keyword, svc_type in service_keywords.items():
                if keyword.lower() in label.lower():
                    service_type = svc_type
                    break
            
            resources.append({
                "id": node_id,
                "name": label,
                "type": service_type,
                "details": {}
            })
        
        return resources
    
    def _extract_mermaid_relationships(self, mermaid_content: str) -> List[Dict[str, str]]:
        """Extract relationships from Mermaid diagram"""
        relationships = []
        
        # Simple pattern matching for connections
        # Supports patterns like: node1 --> node2, node1 -->|label| node2
        pattern = r'(\w+)\s*(?:-->|==>\|.*?\||--)\s*(\w+)'
        matches = re.findall(pattern, mermaid_content)
        
        for source, target in matches:
            relationships.append({
                "from": source,
                "to": target,
                "type": "connection"
            })
        
        return relationships
    
    def _extract_project_name(self, architecture: Dict[str, Any]) -> str:
        """Extract or generate a project name from architecture"""
        # Try to use description
        if "description" in architecture and architecture["description"]:
            name = architecture["description"].lower()
            name = re.sub(r'[^a-z0-9_-]', '_', name)
            return name[:50]
        
        # Try to generate from resources
        resources = architecture.get("resources", [])
        if resources:
            primary_resource = resources[0]
            resource_type = primary_resource.get("type", "infra")
            return f"{resource_type}_architecture"
        
        return "aws_architecture"
