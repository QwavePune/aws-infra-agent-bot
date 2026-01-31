import os
import sys
from dotenv import load_dotenv
from langchain_classic.agents import initialize_agent, AgentType
from langchain_classic.memory import ConversationBufferMemory
from llm_config import select_llm_interactive, initialize_llm
from terraform_tools import get_terraform_tools

# Load environment variables
load_dotenv()

print("=" * 60)
print("LangChain Terraform AWS Agent")
print("=" * 60)
print()

# Check if LLM is specified via environment variable
llm_provider = os.getenv("LLM_PROVIDER", "").lower()

if not llm_provider:
    llm_provider = select_llm_interactive()

print(f"\n[INFO] Initializing {llm_provider.upper()}...")

try:
    # Initialize the selected LLM
    llm = initialize_llm(llm_provider, temperature=0)
    print(f"✅ {llm_provider.upper()} initialized successfully!")
except Exception as e:
    print(f"\n❌ Error initializing {llm_provider}: {e}")
    sys.exit(1)

# Get Terraform tools
tools = get_terraform_tools()

# Set up memory
memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

# Initialize the agent
agent = initialize_agent(
    tools,
    llm,
    agent=AgentType.CHAT_CONVERSATIONAL_REACT_DESCRIPTION,
    verbose=True,
    memory=memory
)

print("\n" + "=" * 60)
print("Terraform Agent - Ready to deploy infrastructure on AWS")
print("=" * 60)
print("Example tasks:")
print("  'Create a VPC in us-east-1'")
print("  'Deploy an S3 bucket with a specific name'")
print("  'Show me the current terraform plan'")
print("=" * 60)
print()

while True:
    try:
        user_query = input("You: ").strip()

        if user_query.lower() in ["quit", "exit", "q", "x"]:
            print("\n👋 Goodbye!")
            break

        if not user_query:
            continue

        print("\n🔄 Processing...")
        response = agent.run(input=user_query)

        print("\nAgent:")
        print("-" * 60)
        print(response)
        print()

    except KeyboardInterrupt:
        print("\n\n👋 Interrupted. Goodbye!")
        break
    except Exception as e:
        print(f"\n❌ Error: {e}\n")
