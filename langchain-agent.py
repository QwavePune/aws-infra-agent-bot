import os
import keyring
from dotenv import load_dotenv
from langchain_perplexity import ChatPerplexity

# Load environment variables from .env file as fallback
load_dotenv()

# --- Retrieve API Key Securely ---
# Try in order: Keychain -> Azure KeyVault -> .env -> Environment variable

SERVICE_NAME = "langchain-agent"
USERNAME = "perplexity"
SECRET_NAME = "perplexity-api-key"

PERPLEXITY_API_KEY = None

# 1. Try local keyring first (most efficient for local machines)
try:
    PERPLEXITY_API_KEY = keyring.get_password(SERVICE_NAME, USERNAME)
    if PERPLEXITY_API_KEY:
        print("[INFO] Using API key from local keyring")
except:
    pass

# 2. Try Azure KeyVault if available and no local key found
if not PERPLEXITY_API_KEY:
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
        
        keyvault_url = os.getenv("AZURE_KEYVAULT_URL")
        if keyvault_url:
            credential = DefaultAzureCredential()
            client = SecretClient(vault_url=keyvault_url, credential=credential)
            secret = client.get_secret(SECRET_NAME)
            PERPLEXITY_API_KEY = secret.value
            print("[INFO] Using API key from Azure KeyVault")
    except:
        pass

# 3. Fall back to .env file
if not PERPLEXITY_API_KEY:
    PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
    if PERPLEXITY_API_KEY:
        print("[INFO] Using API key from .env file")

# 4. Fall back to environment variable
if not PERPLEXITY_API_KEY:
    PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
    if PERPLEXITY_API_KEY:
        print("[INFO] Using API key from environment variable")

if not PERPLEXITY_API_KEY:
    raise ValueError(
        "PERPLEXITY_API_KEY not found.\n"
        "Please set it using one of these methods:\n"
        "  1. Run: python3 setup_keychain.py (recommended - interactive setup)\n"
        "     - Option 1: Local keyring (macOS/Windows/Linux)\n"
        "     - Option 2: Azure KeyVault (cloud-based)\n"
        "  2. Set PERPLEXITY_API_KEY in your .env file\n"
        "  3. Set PERPLEXITY_API_KEY environment variable"
    )

# LLM with Perplexity
llm = ChatPerplexity(
    api_key=PERPLEXITY_API_KEY,
    model="sonar",
    temperature=0
)

# Simple example - invoke the LLM directly
print("=" * 50)
print("Running agent with Perplexity API")
print("=" * 50)

response = llm.invoke("What is 87 * 45? And write a short poem about calculators.")
print("\nFINAL RESULT:")
print(response.content)
