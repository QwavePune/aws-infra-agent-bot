import os
import keyring
from dotenv import load_dotenv
from langchain_perplexity import ChatPerplexity
from langchain_core.messages import HumanMessage, AIMessage

# Load environment variables from .env file as fallback
load_dotenv()

# --- Retrieve API Key Securely ---
# Try in order: Keyring -> Azure KeyVault -> AWS Secrets Manager -> .env -> Environment variable

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

# 3. Try AWS Secrets Manager if available and no key found yet
if not PERPLEXITY_API_KEY:
    try:
        import boto3
        
        aws_region = os.getenv("AWS_REGION")
        aws_secret_name = os.getenv("AWS_SECRET_NAME", SECRET_NAME)
        
        if aws_region:
            client = boto3.client("secretsmanager", region_name=aws_region)
            secret = client.get_secret_value(SecretId=aws_secret_name)
            PERPLEXITY_API_KEY = secret.get("SecretString")
            if PERPLEXITY_API_KEY:
                print("[INFO] Using API key from AWS Secrets Manager")
    except:
        pass

# 4. Fall back to .env file
if not PERPLEXITY_API_KEY:
    PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
    if PERPLEXITY_API_KEY:
        print("[INFO] Using API key from .env file")

# 5. Fall back to environment variable
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
        "     - Option 3: AWS Secrets Manager (cloud-based)\n"
        "  2. Set PERPLEXITY_API_KEY in your .env file\n"
        "  3. Set PERPLEXITY_API_KEY environment variable"
    )

# LLM with Perplexity
llm = ChatPerplexity(
    api_key=PERPLEXITY_API_KEY,
    model="sonar",
    temperature=0
)

# Interactive query loop with conversation history
print("=" * 50)
print("LangChain Perplexity Agent - Conversational")
print("=" * 50)
print("Type 'quit', 'exit', 'q', or 'x' to exit")
print("Type 'clear' to reset conversation history")
print("=" * 50)
print()

# Store conversation history
conversation_history = []

while True:
    try:
        user_query = input("You: ").strip()
        
        # Check for exit commands
        if user_query.lower() in ["quit", "exit", "q", "x"]:
            print("\n👋 Goodbye!")
            break
        
        # Check for clear history command
        if user_query.lower() == "clear":
            conversation_history = []
            print("✅ Conversation history cleared\n")
            continue
        
        if not user_query:
            print("❌ Error: Query cannot be empty\n")
            continue
        
        # Add user message to history
        conversation_history.append(HumanMessage(content=user_query))
        
        print("\n🔄 Processing your query...")
        print("-" * 50)
        
        # Invoke with full conversation history
        response = llm.invoke(conversation_history)
        
        # Add AI response to history
        conversation_history.append(AIMessage(content=response.content))
        
        print()
        print("Agent:")
        print("-" * 50)
        print(response.content)
        print()
        
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted by user. Goodbye!")
        break
    except Exception as e:
        print(f"\n❌ Error: {e}\n")
