#!/usr/bin/env python3
"""
Setup script to securely store Perplexity API key in:
1. Local system keyring (macOS Keychain, Windows Credential Manager, Linux Secret Service)
2. Azure KeyVault (cloud-based)
3. AWS Secrets Manager (cloud-based)

Usage:
    python3 setup_keychain.py
    
This will prompt you to choose a storage backend and securely store your API key.
"""

import keyring
import getpass
import os
import sys
from pathlib import Path

# Azure imports (optional)
try:
    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient
    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False

# AWS imports (optional)
try:
    import boto3
    AWS_AVAILABLE = True
except ImportError:
    AWS_AVAILABLE = False

SERVICE_NAME = "langchain-agent"
USERNAME = "perplexity"
SECRET_NAME = "perplexity-api-key"


def setup_local_keyring():
    """Securely store API key in local system keyring."""
    print("\n" + "=" * 60)
    print("Local Keyring Setup")
    print("=" * 60)
    print()
    
    # Get API key from user
    api_key = getpass.getpass(
        "Enter your Perplexity API key (input will be hidden): "
    )
    
    if not api_key:
        print("❌ Error: API key cannot be empty")
        return False
    
    try:
        # Store in local keyring
        keyring.set_password(SERVICE_NAME, USERNAME, api_key)
        print()
        print("✅ Successfully stored API key in local keyring!")
        print(f"   Service: {SERVICE_NAME}")
        print(f"   Username: {USERNAME}")
        print(f"   Backend: {keyring.get_keyring().__class__.__name__}")
        print()
        print("You can now run: python3 langchain-agent.py")
        return True
    except Exception as e:
        print(f"❌ Error storing in local keyring: {e}")
        return False


def setup_azure_keyvault():
    """Securely store API key in Azure KeyVault."""
    if not AZURE_AVAILABLE:
        print("❌ Azure packages not installed.")
        print("   Install with: pip install azure-identity azure-keyvault-secrets")
        return False
    
    print("\n" + "=" * 60)
    print("Azure KeyVault Setup")
    print("=" * 60)
    print()
    
    # Get KeyVault URL
    keyvault_url = input(
        "Enter your Azure KeyVault URL (e.g., https://mykeyvault.vault.azure.net/): "
    ).strip()
    
    if not keyvault_url:
        print("❌ Error: KeyVault URL cannot be empty")
        return False
    
    # Get API key from user
    api_key = getpass.getpass(
        "Enter your Perplexity API key (input will be hidden): "
    )
    
    if not api_key:
        print("❌ Error: API key cannot be empty")
        return False
    
    try:
        print("\nAuthenticating to Azure...")
        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=keyvault_url, credential=credential)
        
        print("Storing secret in Azure KeyVault...")
        client.set_secret(SECRET_NAME, api_key)
        
        print()
        print("✅ Successfully stored API key in Azure KeyVault!")
        print(f"   KeyVault URL: {keyvault_url}")
        print(f"   Secret Name: {SECRET_NAME}")
        print()
        
        # Save KeyVault URL to .env for easy access
        env_file = Path(".env")
        if env_file.exists():
            with open(env_file, "a") as f:
                f.write(f"\nAZURE_KEYVAULT_URL={keyvault_url}\n")
        else:
            with open(env_file, "w") as f:
                f.write(f"AZURE_KEYVAULT_URL={keyvault_url}\n")
        
        print("Saved KeyVault URL to .env")
        print("You can now run: python3 langchain-agent.py")
        return True
        
    except Exception as e:
        print(f"❌ Error storing in Azure KeyVault: {e}")
        print("\nMake sure you have:")
        print("1. Azure CLI installed and authenticated (az login)")
        print("2. Permissions to manage secrets in the KeyVault")
        print("3. The KeyVault URL is correct")
        return False


def setup_aws_secrets_manager():
    """Securely store API key in AWS Secrets Manager."""
    if not AWS_AVAILABLE:
        print("❌ AWS packages not installed.")
        print("   Install with: pip install boto3")
        return False
    
    print("\n" + "=" * 60)
    print("AWS Secrets Manager Setup")
    print("=" * 60)
    print()
    
    # Get AWS region
    aws_region = input(
        "Enter your AWS region (e.g., us-east-1, us-west-2): "
    ).strip()
    
    if not aws_region:
        print("❌ Error: AWS region cannot be empty")
        return False
    
    # Get secret name
    secret_name = input(
        f"Enter secret name (default: {SECRET_NAME}): "
    ).strip()
    
    if not secret_name:
        secret_name = SECRET_NAME
    
    # Get API key from user
    api_key = getpass.getpass(
        "Enter your Perplexity API key (input will be hidden): "
    )
    
    if not api_key:
        print("❌ Error: API key cannot be empty")
        return False
    
    try:
        print("\nConnecting to AWS...")
        # Create Secrets Manager client
        client = boto3.client("secretsmanager", region_name=aws_region)
        
        print("Storing secret in AWS Secrets Manager...")
        
        try:
            # Try to create the secret
            response = client.create_secret(
                Name=secret_name,
                SecretString=api_key,
                Description="Perplexity API Key for LangChain Agent"
            )
            print(f"✅ Secret created with ARN: {response['ARN']}")
        except client.exceptions.ResourceExistsException:
            # If secret exists, update it
            response = client.update_secret(
                SecretId=secret_name,
                SecretString=api_key
            )
            print(f"✅ Secret updated with ARN: {response['ARN']}")
        
        print()
        print("✅ Successfully stored API key in AWS Secrets Manager!")
        print(f"   Region: {aws_region}")
        print(f"   Secret Name: {secret_name}")
        print()
        
        # Save AWS config to .env for easy access
        env_file = Path(".env")
        env_content = f"AWS_REGION={aws_region}\nAWS_SECRET_NAME={secret_name}\n"
        
        if env_file.exists():
            with open(env_file, "a") as f:
                f.write(f"\n{env_content}")
        else:
            with open(env_file, "w") as f:
                f.write(env_content)
        
        print("Saved AWS config to .env")
        print("You can now run: python3 langchain-agent.py")
        return True
        
    except Exception as e:
        print(f"❌ Error storing in AWS Secrets Manager: {e}")
        print("\nMake sure you have:")
        print("1. AWS CLI configured (aws configure)")
        print("2. AWS credentials with Secrets Manager permissions")
        print("3. Correct region name")
        return False


def verify_setup():
    """Verify which storage backend is configured."""
    print("\n" + "=" * 60)
    print("Checking Credential Storage")
    print("=" * 60)
    print()
    
    # Check local keyring
    try:
        api_key = keyring.get_password(SERVICE_NAME, USERNAME)
        if api_key:
            print("✅ API key found in local keyring")
            return True
    except:
        pass
    
    # Check Azure KeyVault
    if AZURE_AVAILABLE:
        try:
            from dotenv import load_dotenv
            load_dotenv()
            keyvault_url = os.getenv("AZURE_KEYVAULT_URL")
            
            if keyvault_url:
                credential = DefaultAzureCredential()
                client = SecretClient(vault_url=keyvault_url, credential=credential)
                secret = client.get_secret(SECRET_NAME)
                if secret:
                    print("✅ API key found in Azure KeyVault")
                    return True
        except:
            pass
    
    # Check AWS Secrets Manager
    if AWS_AVAILABLE:
        try:
            from dotenv import load_dotenv
            load_dotenv()
            aws_region = os.getenv("AWS_REGION")
            aws_secret_name = os.getenv("AWS_SECRET_NAME", SECRET_NAME)
            
            if aws_region:
                client = boto3.client("secretsmanager", region_name=aws_region)
                try:
                    secret = client.get_secret_value(SecretId=aws_secret_name)
                    if secret:
                        print("✅ API key found in AWS Secrets Manager")
                        return True
                except:
                    pass
        except:
            pass
    
    print("❌ API key not found in any storage backend")
    return False


def main():
    """Main menu."""
    print("\n" + "=" * 60)
    print("Perplexity API Key - Secure Storage Setup")
    print("=" * 60)
    print()
    print("Choose where to store your API key:")
    print()
    print("1. Local Keyring (macOS Keychain, Windows Credential Manager, Linux Secret Service)")
    print("2. Azure KeyVault (cloud-based)")
    print("3. AWS Secrets Manager (cloud-based)")
    
    if not AZURE_AVAILABLE:
        print("   (Azure not available - install with: pip install azure-identity azure-keyvault-secrets)")
    
    if not AWS_AVAILABLE:
        print("   (AWS not available - install with: pip install boto3)")
    
    print()
    choice = input("Enter your choice (1, 2, or 3): ").strip()
    
    if choice == "1":
        setup_local_keyring()
    elif choice == "2":
        if AZURE_AVAILABLE:
            setup_azure_keyvault()
        else:
            print("❌ Azure packages not installed")
            print("   Install with: pip install azure-identity azure-keyvault-secrets")
            sys.exit(1)
    elif choice == "3":
        if AWS_AVAILABLE:
            setup_aws_secrets_manager()
        else:
            print("❌ AWS packages not installed")
            print("   Install with: pip install boto3")
            sys.exit(1)
    else:
        print("❌ Invalid choice")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "verify":
            verify_setup()
        elif sys.argv[1] == "local":
            setup_local_keyring()
        elif sys.argv[1] == "azure":
            setup_azure_keyvault()
        elif sys.argv[1] == "aws":
            setup_aws_secrets_manager()
        else:
            print(f"Unknown command: {sys.argv[1]}")
            print("Usage: python3 setup_keychain.py [verify|local|azure|aws]")
    else:
        main()
