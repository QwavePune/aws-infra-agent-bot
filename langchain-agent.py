import os
import sys
import logging
from datetime import datetime
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage
from llm_config import select_llm_interactive, select_credential_source_interactive, initialize_llm

# Configure logging with best practices
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('.agent-session.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Log session start
logger.info("=" * 80)
logger.info("LangChain Multi-LLM Agent Session Started")
logger.info("=" * 80)

# Determine which LLM to use
print("=" * 60)
print("LangChain Multi-LLM Agent")
print("=" * 60)
print()

# Check if LLM is specified via environment variable
llm_provider = os.getenv("LLM_PROVIDER", "").lower()

if llm_provider:
    print(f"[INFO] Using LLM provider from environment: {llm_provider}")
    logger.info(f"LLM Provider: {llm_provider.upper()} (from LLM_PROVIDER environment variable)")
else:
    # Ask user to select LLM
    llm_provider = select_llm_interactive()
    logger.info(f"LLM Provider: {llm_provider.upper()} (selected interactively)")

print(f"\n[INFO] Initializing {llm_provider.upper()}...")

try:
    # Select credential source
    credential_source = select_credential_source_interactive()
    
    # Initialize the selected LLM
    llm = initialize_llm(llm_provider, temperature=0, preferred_source=credential_source)
    print(f"✅ {llm_provider.upper()} initialized successfully!\n")
    logger.info(f"LLM initialization successful - Provider: {llm_provider.upper()}, Model: {getattr(llm, 'model_name', getattr(llm, 'model', 'unknown'))}")
except Exception as e:
    print(f"\n❌ Error initializing {llm_provider}: {e}")
    logger.error(f"Failed to initialize LLM provider '{llm_provider}': {str(e)}", exc_info=True)
    sys.exit(1)

# Interactive query loop with conversation history
print("=" * 60)
print("Conversational Agent - Type 'help' for commands")
print("=" * 60)
print("Commands:")
print("  quit/exit/q/x  - Exit the agent")
print("  clear          - Reset conversation history")
print("  help           - Show this help message")
print("=" * 60)
print()

# Store conversation history
conversation_history = []

while True:
    try:
        user_query = input("You: ").strip()
        
        # Check for exit commands
        if user_query.lower() in ["quit", "exit", "q", "x"]:
            logger.info("Agent session ended by user (exit command)")
            print("\n👋 Goodbye!")
            break
        
        # Check for help command
        if user_query.lower() == "help":
            print("\nCommands:")
            print("  quit/exit/q/x  - Exit the agent")
            print("  clear          - Reset conversation history")
            print("  help           - Show this help message")
            print()
            continue
        
        # Check for clear history command
        if user_query.lower() == "clear":
            conversation_history = []
            logger.info("Conversation history cleared by user")
            print("✅ Conversation history cleared\n")
            continue
        
        if not user_query:
            print("❌ Error: Query cannot be empty\n")
            continue
        
        # Log query processing (without logging the query content for privacy)
        logger.debug(f"Processing user query (length: {len(user_query)} chars, history_size: {len(conversation_history)} messages)")
        
        # Add user message to history
        conversation_history.append(HumanMessage(content=user_query))
        
        print("\n🔄 Processing your query...")
        print("-" * 60)
        
        # Invoke with full conversation history
        response = llm.invoke(conversation_history)
        
        # Add AI response to history
        conversation_history.append(AIMessage(content=response.content))
        
        print()
        print("Agent:")
        print("-" * 60)
        print(response.content)
        print()
        
        # Log response processing (without logging response content)
        logger.debug(f"Response generated (length: {len(response.content)} chars, total_messages: {len(conversation_history)})")
        
    except KeyboardInterrupt:
        logger.info("Agent session interrupted by user (Ctrl+C)")
        print("\n\n👋 Interrupted by user. Goodbye!")
        break
    except Exception as e:
        logger.error(f"Error processing query: {str(e)}", exc_info=True)
        print(f"\n❌ Error: {e}\n")
