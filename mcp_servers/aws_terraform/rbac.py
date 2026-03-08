"""AWS RBAC helpers for MCP server."""

import logging
import os
from typing import Any, Dict, List, Optional

import boto3

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
            
            logger.info(f"AWS Identity Successfully Retrieved: {self.identity.get('Arn')}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize AWS clients: {str(e)}")
            self.identity = None
            return False

    def get_credentials_env(self) -> Dict[str, str]:
        """Get active AWS credentials as environment variables for subprocesses"""
        try:
            session = boto3.Session()
            creds = session.get_credentials()
            if not creds:
                return {}
            
            frozen = creds.get_frozen_credentials()
            env = {
                "AWS_ACCESS_KEY_ID": frozen.access_key,
                "AWS_SECRET_ACCESS_KEY": frozen.secret_key,
            }
            if frozen.token:
                env["AWS_SESSION_TOKEN"] = frozen.token
                
            region = session.region_name or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
            if region:
                env["AWS_REGION"] = region
                env["AWS_DEFAULT_REGION"] = region
                
            return env
        except Exception as e:
            logger.warning(f"Could not extract session credentials: {e}")
            return {}
    
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
            # Root user check - SimulatePrincipalPolicy doesn't support the root user ARN
            if self.identity and self.identity.get("Arn") and ":root" in self.identity["Arn"]:
                logger.info("Root user detected, skipping permission check (Full Access)")
                return True

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
            # Default to allowing if check fails (most common for restricted accounts or Root)
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
    
    def get_existing_security_group(self, sg_name: str, region: str) -> Optional[str]:
        """
        Query for an existing security group by name in a region.
        
        Args:
            sg_name: Security group name to search for
            region: AWS region
            
        Returns:
            Security group ID if found, None otherwise
        """
        try:
            ec2_client = boto3.client('ec2', region_name=region)
            response = ec2_client.describe_security_groups(
                Filters=[{'Name': 'group-name', 'Values': [sg_name]}]
            )
            
            if response.get('SecurityGroups'):
                sg_id = response['SecurityGroups'][0]['GroupId']
                logger.info(f"Found existing security group '{sg_name}' in {region}: {sg_id}")
                return sg_id
            
            logger.debug(f"No existing security group '{sg_name}' found in {region}")
            return None
        except Exception as e:
            logger.warning(f"Error querying security groups in {region}: {e}")
            return None
