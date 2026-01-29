#!/usr/bin/env python3
"""
Setup script to securely store Perplexity API key in either:
1. Local system keyring (macOS Keychain, Windows Credential Manager, Linux Secret Service)
2. Azure KeyVault (cloud-based, cross-platform)

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
        # Use DefaultAzureCredential which supports:
        # - Environment variables (AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID)
        # - Azure CLI authentication (az login)
        # - Managed Identity (for Azure services)
        # - Visual Studio Code authentication
        credential = DefaultAzureCredential()
        
        # Create KeyVault client
        client = SecretClient(vault_url=keyvault_url, credential=credential)
        
        print("Storing secret in Azure KeyVault...")
        # Store the secret
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
    print("2. Azure KeyVault (cloud-based, cross-platform)")
    
    if not AZURE_AVAILABLE:
        print("   (Azure not available - install with: pip install azure-identity azure-keyvault-secrets)")
    
    print()
    choice = input("Enter your choice (1 or 2): ").strip()
    
    if choice == "1":
        setup_local_keyring()
    elif choice == "2":
        if AZURE_AVAILABLE:
            setup_azure_keyvault()
        else:
            print("❌ Azure packages not installed")
            print("   Install with: pip install azure-identity azure-keyvault-secrets")
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
        else:
            print(f"Unknown command: {sys.argv[1]}")
            print("Usage: python3 setup_keychain.py [verify|local|azure]")
    else:
        main()
