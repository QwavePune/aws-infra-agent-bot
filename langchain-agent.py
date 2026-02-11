import os
import sys
import logging
import json
from datetime import datetime
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from llm_config import select_llm_interactive, select_credential_source_interactive, initialize_llm

# Import MCP server
try:
    from mcp_servers.aws_terraform_server import mcp_server as aws_mcp
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    aws_mcp = None

# Configure logging
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
logger.info("AWS Infra CLI Agent Session Started")
logger.info("=" * 80)

print("=" * 60)
print("AWS Infrastructure CLI Agent")
print("=" * 60)
print()

# 1. AWS Profile Selection
current_profile = os.environ.get("AWS_PROFILE", "default")
change_profile = input(f"Current AWS Profile: {current_profile}. Change it? (y/N): ").lower()
if change_profile == 'y':
    new_profile = input("Enter AWS Profile name: ").strip()
    if new_profile:
        os.environ["AWS_PROFILE"] = new_profile
        current_profile = new_profile
        print(f"✅ AWS_PROFILE set to: {current_profile}")

# 2. LLM Provider Selection
llm_provider = os.getenv("LLM_PROVIDER", "").lower()
if not llm_provider:
    llm_provider = select_llm_interactive()

print(f"\n[INFO] Initializing {llm_provider.upper()}...")

try:
    credential_source = select_credential_source_interactive()
    llm = initialize_llm(llm_provider, temperature=0, preferred_source=credential_source)
    
    # Bind tools if MCP is available
    if MCP_AVAILABLE and aws_mcp:
        tools = aws_mcp.list_tools()
        try:
            llm = llm.bind_tools(tools)
            print(f"✅ {len(tools)} AWS Tools bound to agent.")
        except Exception as tool_err:
            logger.warning(f"Failed to bind tools: {tool_err}")
            
    print(f"✅ {llm_provider.upper()} initialized successfully!\n")
    
    # Verify AWS Identity
    if MCP_AVAILABLE and aws_mcp:
        print("Checking AWS Identity...")
        aws_mcp.rbac.initialize()
        info = aws_mcp.rbac.get_user_info()
        if "error" not in info:
            print(f"👤 Identity: {info.get('user_arn')}")
            print(f"🏢 Account: {info.get('account_id')}")
        else:
            print(f"⚠️  Note: {info.get('error')}. Run 'aws sso login --profile {current_profile}' if needed.")
    
except Exception as e:
    print(f"\n❌ Initialization Error: {e}")
    logger.error(f"Failed to initialize: {str(e)}", exc_info=True)
    sys.exit(1)

# Interactive query loop
print("\n" + "=" * 60)
print("Conversational Agent - Type 'help' for commands")
print("=" * 60)

# Initialize conversation with the strict system prompt from agui_server
system_prompt = (
    "You are a strict AWS Infrastructure Provisioning Agent. "
    "Your main purpose is to interact with AWS through the provided MCP tools. "
    "CRITICAL: ALWAYS try to use the 'get_user_permissions' or 'get_infrastructure_state' tools before claiming you lack access or login info. "
    "Never assume the user is logged out just because you haven't run a tool yet. "
    "If a tool fails with a credential error, then and only then should you ask the user to check their login. "
    "To build infrastructure: 1. Generate the project/config 2. Run terraform_plan 3. Run terraform_apply. "
    "If user says 'apply' or 'execute', you MUST call 'terraform_apply' with the correct project name. "
    "Be concise and technical. Report tool outputs directly."
)

conversation_history = [SystemMessage(content=system_prompt)]

while True:
    try:
        user_query = input("\nYou: ").strip()
        
        if user_query.lower() in ["quit", "exit", "q", "x"]:
            print("\n👋 Goodbye!")
            break
        
        if user_query.lower() == "help":
            print("\nCommands: quit, exit, clear, help")
            continue
            
        if user_query.lower() == "clear":
            conversation_history = [SystemMessage(content=system_prompt)]
            print("✅ Conversation history cleared")
            continue
            
        if not user_query:
            continue
            
        conversation_history.append(HumanMessage(content=user_query))
        print("\n🔄 Processing...")
        
        # Tool Calling Loop (matches agui_server logic)
        max_iterations = 5
        iteration = 0
        
        while iteration < max_iterations:
            response = llm.invoke(conversation_history)
            conversation_history.append(response)
            
            # Check for tool calls
            if hasattr(response, "tool_calls") and response.tool_calls:
                print(f"🛠️  Agent requesting {len(response.tool_calls)} tool(s)...")
                
                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    tool_call_id = tool_call["id"]
                    
                    print(f"  👉 Executing {tool_name}...")
                    
                    if MCP_AVAILABLE and aws_mcp:
                        try:
                            result = aws_mcp.execute_tool(tool_name, tool_args)
                            # Display tool result concisely
                            status = "✅" if result.get("success", False) else "❌"
                            print(f"  {status} Result: {str(result.get('message', result.get('error', 'Success')))[:200]}...")
                            
                            conversation_history.append(ToolMessage(
                                content=json.dumps(result),
                                tool_call_id=tool_call_id
                            ))
                        except Exception as tool_err:
                            print(f"  ❌ Tool Error: {tool_err}")
                            conversation_history.append(ToolMessage(
                                content=json.dumps({"success": False, "error": str(tool_err)}),
                                tool_call_id=tool_call_id
                            ))
                    else:
                        conversation_history.append(ToolMessage(
                            content=json.dumps({"success": False, "error": "MCP server not available"}),
                            tool_call_id=tool_call_id
                        ))
                
                iteration += 1
                continue # Re-invoke LLM with results
            else:
                # No more tool calls, print final response
                print("\nAgent:")
                print("-" * 60)
                print(response.content)
                break
                
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
        break
    except Exception as e:
        print(f"\n❌ Error: {e}")
        logger.error(f"Loop error: {str(e)}", exc_info=True)
