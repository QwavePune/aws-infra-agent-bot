#!/usr/bin/env python3
"""
Setup script to securely store API keys for different LLM providers in:
1. Local system keyring (macOS Keychain, Windows Credential Manager, Linux Secret Service)
2. Azure KeyVault (cloud-based)
3. AWS Secrets Manager (cloud-based)

Usage:
    python3 setup_keychain.py
    
This will prompt you to choose an LLM provider and a storage backend.
"""

import keyring
import getpass
import os
import sys
from pathlib import Path

# Import LLM configurations to get supported providers
try:
    from llm_config import SUPPORTED_LLMS
except ImportError:
    # Minimal fallback if import fails
    SUPPORTED_LLMS = {
        "perplexity": {"name": "Perplexity", "requires_api_key": True},
        "openai": {"name": "OpenAI", "requires_api_key": True},
        "gemini": {"name": "Google Gemini", "requires_api_key": True},
        "claude": {"name": "Anthropic Claude", "requires_api_key": True}
    }

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

def select_provider():
    """Ask the user to select an LLM provider."""
    print("\n" + "=" * 60)
    print("Select LLM Provider")
    print("=" * 60)
    
    # Filter only providers that require an API key
    providers = {k: v for k, v in SUPPORTED_LLMS.items() if v.get("requires_api_key", True)}
    
    provider_keys = list(providers.keys())
    for i, key in enumerate(provider_keys, 1):
        name = providers[key].get("name", key.capitalize())
        print(f"{i}. {name}")
    
    print()
    try:
        choice = int(input(f"Enter your choice (1-{len(provider_keys)}): ").strip())
        if 1 <= choice <= len(provider_keys):
            selected_key = provider_keys[choice-1]
            return selected_key, providers[selected_key].get("name", selected_key.capitalize())
    except (ValueError, IndexError):
        pass
    
    print("❌ Invalid choice")
    sys.exit(1)

def setup_local_keyring(provider_key, provider_name):
    """Securely store API key in local system keyring."""
    print("\n" + "=" * 60)
    print(f"Local Keyring Setup - {provider_name}")
    print("=" * 60)
    print()
    
    # Get API key from user
    api_key = getpass.getpass(
        f"Enter your {provider_name} API key (input will be hidden): "
    )
    
    if not api_key:
        print("❌ Error: API key cannot be empty")
        return False
    
    try:
        # Store in local keyring
        keyring.set_password(SERVICE_NAME, provider_key, api_key)
        print()
        print(f"✅ Successfully stored {provider_name} API key in local keyring!")
        print(f"   Service: {SERVICE_NAME}")
        print(f"   Username: {provider_key}")
        print(f"   Backend: {keyring.get_keyring().__class__.__name__}")
        print()
        return True
    except Exception as e:
        print(f"❌ Error storing in local keyring: {e}")
        return False


def setup_azure_keyvault(provider_key, provider_name):
    """Securely store API key in Azure KeyVault."""
    if not AZURE_AVAILABLE:
        print("❌ Azure packages not installed.")
        print("   Install with: pip install azure-identity azure-keyvault-secrets")
        return False
    
    print("\n" + "=" * 60)
    print(f"Azure KeyVault Setup - {provider_name}")
    print("=" * 60)
    print()
    
    # Get KeyVault URL
    keyvault_url = input(
        "Enter your Azure KeyVault URL (e.g., https://mykeyvault.vault.azure.net/): "
    ).strip()
    
    if not keyvault_url:
        print("❌ Error: KeyVault URL cannot be empty")
        return False
    
    secret_name = f"{provider_key}-api-key"
    
    # Get API key from user
    api_key = getpass.getpass(
        f"Enter your {provider_name} API key (input will be hidden): "
    )
    
    if not api_key:
        print("❌ Error: API key cannot be empty")
        return False
    
    try:
        print("\nAuthenticating to Azure...")
        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=keyvault_url, credential=credential)
        
        print(f"Storing secret '{secret_name}' in Azure KeyVault...")
        client.set_secret(secret_name, api_key)
        
        print()
        print(f"✅ Successfully stored {provider_name} API key in Azure KeyVault!")
        print(f"   KeyVault URL: {keyvault_url}")
        print(f"   Secret Name: {secret_name}")
        print()
        
        # Save KeyVault URL to .env for easy access
        env_file = Path(".env")
        env_line = f"AZURE_KEYVAULT_URL={keyvault_url}\n"
        
        if env_file.exists():
            content = env_file.read_text()
            if "AZURE_KEYVAULT_URL" not in content:
                with open(env_file, "a") as f:
                    f.write(f"\n{env_line}")
        else:
            env_file.write_text(env_line)
        
        return True
    except Exception as e:
        print(f"❌ Error storing in Azure KeyVault: {e}")
        return False


def setup_aws_secrets_manager(provider_key, provider_name):
    """Securely store API key in AWS Secrets Manager."""
    if not AWS_AVAILABLE:
        print("❌ AWS packages not installed.")
        print("   Install with: pip install boto3")
        return False
    
    print("\n" + "=" * 60)
    print(f"AWS Secrets Manager Setup - {provider_name}")
    print("=" * 60)
    print()
    
    # Get AWS region
    aws_region = input(
        "Enter your AWS region (e.g., us-east-1, us-west-2): "
    ).strip()
    
    if not aws_region:
        print("❌ Error: AWS region cannot be empty")
        return False
    
    default_secret_name = f"{provider_key}-api-key"
    secret_name = input(
        f"Enter secret name (default: {default_secret_name}): "
    ).strip()
    
    if not secret_name:
        secret_name = default_secret_name
    
    # Get API key from user
    api_key = getpass.getpass(
        f"Enter your {provider_name} API key (input will be hidden): "
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
                Description=f"{provider_name} API Key for LangChain Agent"
            )
            print(f"✅ Secret created with ARN: {response['ARN']}")
        except client.exceptions.ResourceExistsException:
            response = client.update_secret(
                SecretId=secret_name,
                SecretString=api_key
            )
            print(f"✅ Secret updated with ARN: {response['ARN']}")
        
        print()
        print(f"✅ Successfully stored {provider_name} API key in AWS Secrets Manager!")
        print(f"   Region: {aws_region}")
        print(f"   Secret Name: {secret_name}")
        print()
        
        # Save AWS config to .env (using provider-specific prefix if we want multiple)
        env_file = Path(".env")
        env_content = f"AWS_REGION={aws_region}\n{provider_key.upper()}_AWS_SECRET_NAME={secret_name}\n"
        
        with open(env_file, "a" if env_file.exists() else "w") as f:
            f.write(f"\n{env_content}")
            
        return True
    except Exception as e:
        print(f"❌ Error storing in AWS Secrets Manager: {e}")
        return False


def verify_setup():
    """Verify which storage backends are configured for all providers."""
    print("\n" + "=" * 60)
    print("Checking Credential Storage (All Providers)")
    print("=" * 60)
    print()
    
    providers_with_keys = [k for k, v in SUPPORTED_LLMS.items() if v.get("requires_api_key", True)]
    
    overall_found = False
    for provider in providers_with_keys:
        name = SUPPORTED_LLMS[provider].get("name", provider)
        print(f"--- {name} ---")
        found = False
        
        # Check local keyring
        try:
            api_key = keyring.get_password(SERVICE_NAME, provider)
            if api_key:
                print(f"  ✅ Local Keyring: Found")
                found = True
        except: pass
        
        if not found:
            print(f"  ❌ Not found in any local storage")
        else:
            overall_found = True
        print()

    return overall_found


def main():
    """Main menu."""
    provider_key, provider_name = select_provider()
    
    print("\n" + "=" * 60)
    print(f"Secure Storage Setup for {provider_name}")
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
        setup_local_keyring(provider_key, provider_name)
    elif choice == "2":
        if AZURE_AVAILABLE:
            setup_azure_keyvault(provider_key, provider_name)
        else:
            print("❌ Azure packages not installed")
            sys.exit(1)
    elif choice == "3":
        if AWS_AVAILABLE:
            setup_aws_secrets_manager(provider_key, provider_name)
        else:
            print("❌ AWS packages not installed")
            sys.exit(1)
    else:
        print("❌ Invalid choice")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "verify":
            verify_setup()
        else:
            # For direct commands like 'python3 setup_keychain.py local', 
            # we still need to know WHICH provider.
            p_key, p_name = select_provider()
            if cmd == "local":
                setup_local_keyring(p_key, p_name)
            elif cmd == "azure":
                setup_azure_keyvault(p_key, p_name)
            elif cmd == "aws":
                setup_aws_secrets_manager(p_key, p_name)
            else:
                print(f"Unknown command: {cmd}")
                print("Usage: python3 setup_keychain.py [verify|local|azure|aws]")
    else:
        main()
