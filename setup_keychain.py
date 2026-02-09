#!/usr/bin/env python3
"""
Setup script to securely store LLM API keys in:
1. Local system keyring (macOS Keychain, Windows Credential Manager, Linux Secret Service)
2. Azure KeyVault (cloud-based)
3. AWS Secrets Manager (cloud-based)

Usage:
    python3 setup_keychain.py
    
This will prompt you to choose a provider and storage backend and securely store your API key.
"""

import keyring
import getpass
import os
import sys
from pathlib import Path
from llm_config import SUPPORTED_LLMS

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


def get_provider_choice():
    """Ask user to select an LLM provider."""
    print("\n" + "=" * 60)
    print("Select LLM Provider")
    print("=" * 60)

    providers = [p for p, config in SUPPORTED_LLMS.items() if config["requires_api_key"]]

    for i, p in enumerate(providers, 1):
        print(f"{i}. {SUPPORTED_LLMS[p]['name']} ({p})")

    while True:
        choice = input(f"\nEnter choice (1-{len(providers)}): ").strip()
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(providers):
                return providers[idx]
        except ValueError:
            if choice in providers:
                return choice
        print("❌ Invalid choice. Please try again.")


def setup_local_keyring(provider):
    """Securely store API key in local system keyring."""
    print("\n" + "=" * 60)
    print(f"Local Keyring Setup - {SUPPORTED_LLMS[provider]['name']}")
    print("=" * 60)
    print()
    
    # Get API key from user
    api_key = getpass.getpass(
        f"Enter your {SUPPORTED_LLMS[provider]['name']} API key (input will be hidden): "
    )
    
    if not api_key:
        print("❌ Error: API key cannot be empty")
        return False
    
    try:
        # Store in local keyring
        keyring.set_password(SERVICE_NAME, provider, api_key)
        print()
        print(f"✅ Successfully stored {provider} API key in local keyring!")
        print(f"   Service: {SERVICE_NAME}")
        print(f"   Username: {provider}")
        print(f"   Backend: {keyring.get_keyring().__class__.__name__}")
        print()
        return True
    except Exception as e:
        print(f"❌ Error storing in local keyring: {e}")
        return False


def setup_azure_keyvault(provider):
    """Securely store API key in Azure KeyVault."""
    if not AZURE_AVAILABLE:
        print("❌ Azure packages not installed.")
        print("   Install with: pip install azure-identity azure-keyvault-secrets")
        return False
    
    print("\n" + "=" * 60)
    print(f"Azure KeyVault Setup - {SUPPORTED_LLMS[provider]['name']}")
    print("=" * 60)
    print()
    
    # Get KeyVault URL
    keyvault_url = os.getenv("AZURE_KEYVAULT_URL")
    if not keyvault_url:
        keyvault_url = input(
            "Enter your Azure KeyVault URL (e.g., https://mykeyvault.vault.azure.net/): "
        ).strip()
    else:
        print(f"Using KeyVault URL from environment: {keyvault_url}")
    
    if not keyvault_url:
        print("❌ Error: KeyVault URL cannot be empty")
        return False
    
    # Get API key from user
    api_key = getpass.getpass(
        f"Enter your {SUPPORTED_LLMS[provider]['name']} API key (input will be hidden): "
    )
    
    if not api_key:
        print("❌ Error: API key cannot be empty")
        return False
    
    secret_name = f"{provider}-api-key"

    try:
        print("\nAuthenticating to Azure...")
        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=keyvault_url, credential=credential)
        
        print(f"Storing secret '{secret_name}' in Azure KeyVault...")
        client.set_secret(secret_name, api_key)
        
        print()
        print(f"✅ Successfully stored {provider} API key in Azure KeyVault!")
        print(f"   KeyVault URL: {keyvault_url}")
        print(f"   Secret Name: {secret_name}")
        print()
        
        # Save KeyVault URL to .env for easy access
        env_file = Path(".env")
        if env_file.exists():
            content = env_file.read_text()
            if "AZURE_KEYVAULT_URL" not in content:
                with open(env_file, "a") as f:
                    f.write(f"\nAZURE_KEYVAULT_URL={keyvault_url}\n")
        else:
            with open(env_file, "w") as f:
                f.write(f"AZURE_KEYVAULT_URL={keyvault_url}\n")
        
        return True
        
    except Exception as e:
        print(f"❌ Error storing in Azure KeyVault: {e}")
        return False


def setup_aws_secrets_manager(provider):
    """Securely store API key in AWS Secrets Manager."""
    if not AWS_AVAILABLE:
        print("❌ AWS packages not installed.")
        print("   Install with: pip install boto3")
        return False
    
    print("\n" + "=" * 60)
    print(f"AWS Secrets Manager Setup - {SUPPORTED_LLMS[provider]['name']}")
    print("=" * 60)
    print()
    
    # Get AWS region
    aws_region = os.getenv("AWS_REGION")
    if not aws_region:
        aws_region = input(
            "Enter your AWS region (e.g., us-east-1, us-west-2): "
        ).strip()
    else:
        print(f"Using AWS region from environment: {aws_region}")
    
    if not aws_region:
        print("❌ Error: AWS region cannot be empty")
        return False
    
    secret_name = f"{provider}-api-key"
    
    # Get API key from user
    api_key = getpass.getpass(
        f"Enter your {SUPPORTED_LLMS[provider]['name']} API key (input will be hidden): "
    )
    
    if not api_key:
        print("❌ Error: API key cannot be empty")
        return False
    
    try:
        print("\nConnecting to AWS...")
        client = boto3.client("secretsmanager", region_name=aws_region)
        
        print(f"Storing secret '{secret_name}' in AWS Secrets Manager...")
        
        try:
            response = client.create_secret(
                Name=secret_name,
                SecretString=api_key,
                Description=f"{SUPPORTED_LLMS[provider]['name']} API Key for LangChain Agent"
            )
            print(f"✅ Secret created with ARN: {response['ARN']}")
        except client.exceptions.ResourceExistsException:
            response = client.update_secret(
                SecretId=secret_name,
                SecretString=api_key
            )
            print(f"✅ Secret updated with ARN: {response['ARN']}")
        
        print()
        print(f"✅ Successfully stored {provider} API key in AWS Secrets Manager!")
        print(f"   Region: {aws_region}")
        print(f"   Secret Name: {secret_name}")
        print()
        
        # Save AWS config to .env
        env_file = Path(".env")
        env_content = f"AWS_REGION={aws_region}\n"
        
        if env_file.exists():
            content = env_file.read_text()
            if "AWS_REGION" not in content:
                with open(env_file, "a") as f:
                    f.write(f"\n{env_content}")
        else:
            with open(env_file, "w") as f:
                f.write(env_content)
        
        return True
        
    except Exception as e:
        print(f"❌ Error storing in AWS Secrets Manager: {e}")
        return False


def verify_setup():
    """Verify which storage backend is configured."""
    print("\n" + "=" * 60)
    print("Checking Credential Storage")
    print("=" * 60)
    print()
    
    providers = [p for p, config in SUPPORTED_LLMS.items() if config["requires_api_key"]]
    
    for provider in providers:
        found = False
        print(f"Checking {SUPPORTED_LLMS[provider]['name']} ({provider})...")

        # Check local keyring
        try:
            api_key = keyring.get_password(SERVICE_NAME, provider)
            if api_key:
                print(f"  ✅ Found in local keyring")
                found = True
        except:
            pass

        # Check .env / Environment
        env_var = SUPPORTED_LLMS[provider].get("env_var")
        if env_var and os.getenv(env_var):
            print(f"  ✅ Found in environment ({env_var})")
            found = True
            
        if not found:
            print("  ❌ Not found")
    
    return True


def main():
    """Main menu."""
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        verify_setup()
        return

    provider = get_provider_choice()

    print("\n" + "=" * 60)
    print(f"Secure Storage Setup - {SUPPORTED_LLMS[provider]['name']}")
    print("=" * 60)
    print()
    print("Choose where to store your API key:")
    print()
    print("1. Local Keyring (macOS Keychain, Windows Credential Manager, Linux Secret Service)")
    print("2. Azure KeyVault (cloud-based)")
    print("3. AWS Secrets Manager (cloud-based)")
    
    choice = input("\nEnter choice (1, 2, or 3): ").strip()
    
    if choice == "1":
        setup_local_keyring(provider)
    elif choice == "2":
        setup_azure_keyvault(provider)
    elif choice == "3":
        setup_aws_secrets_manager(provider)
    else:
        print("❌ Invalid choice")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nExiting...")
        sys.exit(0)
