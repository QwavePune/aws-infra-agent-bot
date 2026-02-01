"""
LLM Configuration Module

Manages different LLM providers and their API keys.
Supports: OpenAI, Gemini, Claude, Perplexity, Ollama
"""

import os
import keyring
import logging
from typing import Optional

# Configure logger for this module
logger = logging.getLogger(__name__)

# LLM Provider configurations
SUPPORTED_LLMS = {
    "perplexity": {
        "name": "Perplexity (Sonar)",
        "package": "langchain_perplexity",
        "class": "ChatPerplexity",
        "default_model": "sonar",
        "requires_api_key": True,
        "env_var": "PERPLEXITY_API_KEY",
    },
    "openai": {
        "name": "OpenAI (GPT-4)",
        "package": "langchain_openai",
        "class": "ChatOpenAI",
        "default_model": "gpt-4o-mini",
        "requires_api_key": True,
        "env_var": "OPENAI_API_KEY",
    },
    "gemini": {
        "name": "Google Gemini",
        "package": "langchain_google_genai",
        "class": "ChatGoogleGenerativeAI",
        "default_model": "gemini-pro",
        "requires_api_key": True,
        "env_var": "GOOGLE_API_KEY",
    },
    "claude": {
        "name": "Anthropic Claude",
        "package": "langchain_anthropic",
        "class": "ChatAnthropic",
        "default_model": "claude-3-5-sonnet-20241022",
        "requires_api_key": True,
        "env_var": "ANTHROPIC_API_KEY",
    },
    "ollama": {
        "name": "Ollama (Local)",
        "package": "langchain_ollama",
        "class": "ChatOllama",
        "default_model": "llama2",
        "requires_api_key": False,
        "env_var": None,
    },
}


def get_api_key(provider: str, service_name: str = "langchain-agent", preferred_source: Optional[str] = None) -> Optional[str]:
    """
    Retrieve API key for a provider in order of priority:
    1. Local keyring
    2. Azure KeyVault
    3. AWS Secrets Manager
    4. .env file
    5. Environment variable
    
    Args:
        provider: LLM provider name
        service_name: Service name for keyring
        preferred_source: Optional preferred source ('local', 'azure', 'aws', 'env', 'dotenv')
                         If specified, only tries that source
    """
    from dotenv import load_dotenv
    
    load_dotenv()
    
    if provider not in SUPPORTED_LLMS:
        raise ValueError(f"Unsupported LLM provider: {provider}")
    
    config = SUPPORTED_LLMS[provider]
    env_var = config["env_var"]
    secret_name = f"{provider}-api-key"
    
    api_key = None
    
    # If preferred source specified, try only that one
    if preferred_source:
        preferred_source = preferred_source.lower()
        
        if preferred_source == "local":
            try:
                api_key = keyring.get_password(service_name, provider)
                if api_key:
                    logger.info(f"Credential Source: Local Keyring (Service: {service_name}, Username: {provider})")
                    print(f"[INFO] API key retrieved from: Local Keyring")
                    return api_key
            except Exception as e:
                logger.error(f"Failed to retrieve from Local Keyring: {str(e)}")
                raise ValueError(f"Could not retrieve API key from Local Keyring: {str(e)}")
        
        elif preferred_source == "azure":
            try:
                from azure.identity import DefaultAzureCredential
                from azure.keyvault.secrets import SecretClient
                
                keyvault_url = os.getenv("AZURE_KEYVAULT_URL")
                if not keyvault_url:
                    raise ValueError("AZURE_KEYVAULT_URL not set in environment")
                    
                credential = DefaultAzureCredential()
                client = SecretClient(vault_url=keyvault_url, credential=credential)
                secret = client.get_secret(secret_name)
                if secret:
                    logger.info(f"Credential Source: Azure KeyVault (URL: {keyvault_url}, Secret: {secret_name})")
                    print(f"[INFO] API key retrieved from: Azure KeyVault")
                    return secret.value
                else:
                    raise ValueError(f"Secret '{secret_name}' not found in Azure KeyVault")
            except Exception as e:
                logger.error(f"Failed to retrieve from Azure KeyVault: {str(e)}")
                raise ValueError(f"Could not retrieve API key from Azure KeyVault: {str(e)}")
        
        elif preferred_source == "aws":
            try:
                import boto3
                
                aws_region = os.getenv("AWS_REGION")
                if not aws_region:
                    raise ValueError("AWS_REGION not set in environment")
                
                client = boto3.client("secretsmanager", region_name=aws_region)
                secret = client.get_secret_value(SecretId=secret_name)
                api_key = secret.get("SecretString")
                if api_key:
                    # Get AWS account ID and user info for audit logging
                    try:
                        sts_client = boto3.client("sts", region_name=aws_region)
                        identity = sts_client.get_caller_identity()
                        aws_account = identity.get("Account", "unknown")
                        aws_arn = identity.get("Arn", "unknown")
                        logger.info(f"Credential Source: AWS Secrets Manager (Region: {aws_region}, Secret: {secret_name}, Account: {aws_account}, ARN: {aws_arn})")
                    except Exception as audit_e:
                        logger.debug(f"Could not retrieve AWS identity info: {str(audit_e)}")
                        logger.info(f"Credential Source: AWS Secrets Manager (Region: {aws_region}, Secret: {secret_name})")
                    print(f"[INFO] API key retrieved from: AWS Secrets Manager (region: {aws_region})")
                    return api_key
                else:
                    raise ValueError(f"Secret '{secret_name}' not found or empty in AWS Secrets Manager")
            except Exception as e:
                logger.error(f"Failed to retrieve from AWS Secrets Manager: {str(e)}")
                raise ValueError(f"Could not retrieve API key from AWS Secrets Manager: {str(e)}")
        
        elif preferred_source in ("env", "dotenv"):
            if env_var:
                api_key = os.getenv(env_var)
                if api_key:
                    logger.info(f"Credential Source: {'Environment variable' if preferred_source == 'env' else '.env file'} (Variable: {env_var})")
                    print(f"[INFO] API key retrieved from: {env_var}")
                    return api_key
            raise ValueError(f"Could not retrieve API key from environment/dotenv using {env_var}")
        
        else:
            raise ValueError(f"Unknown preferred source: {preferred_source}. Choose from: local, azure, aws, env, dotenv")
    
    # Default behavior: try all sources in order
    # 1. Try local keyring
    try:
        api_key = keyring.get_password(service_name, provider)
        if api_key:
            logger.info(f"Credential Source: Local Keyring (Service: {service_name}, Username: {provider})")
            print(f"[INFO] API key retrieved from: Local Keyring")
            return api_key
    except Exception as e:
        logger.debug(f"Local keyring check failed: {str(e)}")
        pass
    
    # 2. Try Azure KeyVault
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
        
        keyvault_url = os.getenv("AZURE_KEYVAULT_URL")
        if keyvault_url:
            credential = DefaultAzureCredential()
            client = SecretClient(vault_url=keyvault_url, credential=credential)
            secret = client.get_secret(secret_name)
            if secret:
                logger.info(f"Credential Source: Azure KeyVault (URL: {keyvault_url}, Secret: {secret_name})")
                print(f"[INFO] API key retrieved from: Azure KeyVault")
                return secret.value
    except Exception as e:
        logger.debug(f"Azure KeyVault check failed: {str(e)}")
        pass
    
    # 3. Try AWS Secrets Manager
    try:
        import boto3
        
        aws_region = os.getenv("AWS_REGION")
        if aws_region:
            client = boto3.client("secretsmanager", region_name=aws_region)
            try:
                secret = client.get_secret_value(SecretId=secret_name)
                api_key = secret.get("SecretString")
                if api_key:
                    # Get AWS account ID and user info for audit logging
                    try:
                        sts_client = boto3.client("sts", region_name=aws_region)
                        identity = sts_client.get_caller_identity()
                        aws_account = identity.get("Account", "unknown")
                        aws_arn = identity.get("Arn", "unknown")
                        logger.info(f"Credential Source: AWS Secrets Manager (Region: {aws_region}, Secret: {secret_name}, Account: {aws_account}, ARN: {aws_arn})")
                    except Exception as audit_e:
                        logger.debug(f"Could not retrieve AWS identity info: {str(audit_e)}")
                        logger.info(f"Credential Source: AWS Secrets Manager (Region: {aws_region}, Secret: {secret_name})")
                    print(f"[INFO] API key retrieved from: AWS Secrets Manager (region: {aws_region})")
                    return api_key
            except client.exceptions.ResourceNotFoundException:
                logger.debug(f"Secret '{secret_name}' not found in AWS Secrets Manager (region: {aws_region})")
    except Exception as e:
        logger.debug(f"AWS Secrets Manager check failed: {str(e)}")
        pass
    
    # 4. Try .env file
    if env_var:
        api_key = os.getenv(env_var)
        if api_key:
            logger.info(f"Credential Source: .env file (Variable: {env_var})")
            print(f"[INFO] API key retrieved from: .env file ({env_var})")
            return api_key
    
    # 5. Try environment variable (already covered above, but be explicit)
    if env_var:
        api_key = os.getenv(env_var)
        if api_key:
            logger.info(f"Credential Source: Environment variable (Variable: {env_var})")
            print(f"[INFO] API key retrieved from: Environment variable ({env_var})")
            return api_key
    
    logger.warning(f"No API key found for provider '{provider}' in any credential source")
    return None
    """
    Retrieve API key for a provider in order of priority:
    1. Local keyring
    2. Azure KeyVault
    3. AWS Secrets Manager
    4. .env file
    5. Environment variable
    """
    from dotenv import load_dotenv
    
    load_dotenv()
    
    if provider not in SUPPORTED_LLMS:
        raise ValueError(f"Unsupported LLM provider: {provider}")
    
    config = SUPPORTED_LLMS[provider]
    env_var = config["env_var"]
    secret_name = f"{provider}-api-key"
    
    api_key = None
    
    # 1. Try local keyring
    try:
        api_key = keyring.get_password(service_name, provider)
        if api_key:
            logger.info(f"Credential Source: Local Keyring (Service: {service_name}, Username: {provider})")
            print(f"[DEBUG] API key retrieved from: Local Keyring")
            return api_key
    except Exception as e:
        logger.debug(f"Local keyring check failed: {str(e)}")
        pass
    
    # 2. Try Azure KeyVault
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
        
        keyvault_url = os.getenv("AZURE_KEYVAULT_URL")
        if keyvault_url:
            credential = DefaultAzureCredential()
            client = SecretClient(vault_url=keyvault_url, credential=credential)
            secret = client.get_secret(secret_name)
            if secret:
                logger.info(f"Credential Source: Azure KeyVault (URL: {keyvault_url}, Secret: {secret_name})")
                print(f"[DEBUG] API key retrieved from: Azure KeyVault")
                return secret.value
    except Exception as e:
        logger.debug(f"Azure KeyVault check failed: {str(e)}")
        pass
    
    # 3. Try AWS Secrets Manager
    try:
        import boto3
        
        aws_region = os.getenv("AWS_REGION")
        if aws_region:
            client = boto3.client("secretsmanager", region_name=aws_region)
            try:
                secret = client.get_secret_value(SecretId=secret_name)
                api_key = secret.get("SecretString")
                if api_key:
                    # Get AWS account ID and user info for audit logging
                    try:
                        sts_client = boto3.client("sts", region_name=aws_region)
                        identity = sts_client.get_caller_identity()
                        aws_account = identity.get("Account", "unknown")
                        aws_arn = identity.get("Arn", "unknown")
                        logger.info(f"Credential Source: AWS Secrets Manager (Region: {aws_region}, Secret: {secret_name}, Account: {aws_account}, ARN: {aws_arn})")
                    except Exception as audit_e:
                        logger.debug(f"Could not retrieve AWS identity info: {str(audit_e)}")
                        logger.info(f"Credential Source: AWS Secrets Manager (Region: {aws_region}, Secret: {secret_name})")
                    print(f"[DEBUG] API key retrieved from: AWS Secrets Manager (region: {aws_region})")
                    return api_key
            except client.exceptions.ResourceNotFoundException:
                logger.debug(f"Secret '{secret_name}' not found in AWS Secrets Manager (region: {aws_region})")
    except Exception as e:
        logger.debug(f"AWS Secrets Manager check failed: {str(e)}")
        pass
    
    # 4. Try .env file
    if env_var:
        api_key = os.getenv(env_var)
        if api_key:
            logger.info(f"Credential Source: .env file (Variable: {env_var})")
            print(f"[DEBUG] API key retrieved from: .env file ({env_var})")
            return api_key
    
    # 5. Try environment variable (already covered above, but be explicit)
    if env_var:
        api_key = os.getenv(env_var)
        if api_key:
            logger.info(f"Credential Source: Environment variable (Variable: {env_var})")
            print(f"[DEBUG] API key retrieved from: Environment variable ({env_var})")
            return api_key
    
    logger.warning(f"No API key found for provider '{provider}' in any credential source")
    return None


def initialize_llm(provider: str, model: Optional[str] = None, preferred_source: Optional[str] = None, **kwargs):
    """
    Initialize and return an LLM instance for the given provider.
    
    Args:
        provider: LLM provider name (perplexity, openai, gemini, claude, ollama)
        model: Model name (optional, uses default if not specified)
        preferred_source: Optional preferred credential source ('local', 'azure', 'aws', or None for auto-detect)
        **kwargs: Additional arguments to pass to the LLM constructor
    
    Returns:
        Initialized LLM instance
    """
    if provider not in SUPPORTED_LLMS:
        raise ValueError(f"Unsupported LLM provider: {provider}. Choose from: {list(SUPPORTED_LLMS.keys())}")
    
    config = SUPPORTED_LLMS[provider]
    model = model or config["default_model"]
    
    logger.info(f"Initializing LLM - Provider: {provider.upper()}, Model: {model}, Preferred Credential Source: {preferred_source or 'auto-detect'}")
    
    # Get API key if required
    if config["requires_api_key"]:
        api_key = get_api_key(provider, preferred_source=preferred_source)
        if not api_key:
            logger.error(f"API key required for {config['name']} but not found")
            raise ValueError(
                f"API key for {config['name']} not found.\n"
                f"Please set {config['env_var']} or run: python3 setup_keychain.py"
            )
    
    # Import and instantiate the LLM class
    module = __import__(config["package"], fromlist=[config["class"]])
    llm_class = getattr(module, config["class"])
    
    # Build initialization parameters
    llm_params = {"model": model, **kwargs}
    
    # Add API key if required
    if config["requires_api_key"]:
        api_key = get_api_key(provider, preferred_source=preferred_source)
        if provider == "perplexity":
            llm_params["api_key"] = api_key
        elif provider == "openai":
            llm_params["api_key"] = api_key
        elif provider == "gemini":
            llm_params["api_key"] = api_key
        elif provider == "claude":
            llm_params["api_key"] = api_key
    
    # Handle Ollama's special base_url parameter
    if provider == "ollama":
        ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        llm_params["base_url"] = ollama_base_url
        logger.info(f"Ollama Configuration - Base URL: {ollama_base_url}")
    
    llm = llm_class(**llm_params)
    logger.info(f"LLM initialization completed - Provider: {provider.upper()}, Model: {model}, Temperature: {kwargs.get('temperature', 'default')}")
    return llm


def select_credential_source_interactive() -> Optional[str]:
    """Interactively select credential source for API key retrieval."""
    print("\n" + "=" * 60)
    print("Select API Key Location")
    print("=" * 60)
    print()
    print("1. Local Keyring (macOS Keychain, Windows Credential Manager, Linux Secret Service)")
    print("2. Azure KeyVault (cloud-based)")
    print("3. AWS Secrets Manager (cloud-based)")
    print("4. Auto-detect (try all sources in priority order)")
    print()
    
    while True:
        choice = input("Enter your choice (1-4) or press Enter for auto-detect: ").strip()
        
        if choice == "":
            logger.info("Credential source selection: Auto-detect")
            print("[INFO] Using auto-detect mode (priority: Local Keyring → Azure → AWS → Environment)")
            return None  # None means auto-detect
        elif choice == "1":
            logger.info("Credential source selection: Local Keyring")
            return "local"
        elif choice == "2":
            logger.info("Credential source selection: Azure KeyVault")
            return "azure"
        elif choice == "3":
            logger.info("Credential source selection: AWS Secrets Manager")
            return "aws"
        elif choice == "4":
            logger.info("Credential source selection: Auto-detect")
            print("[INFO] Using auto-detect mode (priority: Local Keyring → Azure → AWS → Environment)")
            return None
        else:
            print("❌ Invalid choice. Please enter 1, 2, 3, 4, or press Enter for auto-detect.")


def list_available_llms():
    """Print available LLM providers."""
    print("\n" + "=" * 60)
    print("Available LLM Providers")
    print("=" * 60)
    
    for i, (provider_key, config) in enumerate(SUPPORTED_LLMS.items(), 1):
        key_status = "✓" if config["requires_api_key"] else "✓ (No key needed)"
        print(f"{i}. {config['name']}")
        print(f"   Provider: {provider_key}")
        print(f"   Default Model: {config['default_model']}")
        print(f"   API Key Required: {key_status}")
        if config["env_var"]:
            print(f"   Env Variable: {config['env_var']}")
        print()


def select_llm_interactive():
    """Interactively select an LLM provider."""
    list_available_llms()
    
    providers = list(SUPPORTED_LLMS.keys())
    
    while True:
        choice = input("Enter LLM provider number or name (1-5): ").strip().lower()
        
        # Check if it's a number
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(providers):
                return providers[idx]
        except ValueError:
            pass
        
        # Check if it's a provider name
        if choice in providers:
            return choice
        
        print("❌ Invalid choice. Please try again.")
