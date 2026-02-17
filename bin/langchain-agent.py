import os
import sys
import logging
import json
from datetime import datetime
from dotenv import load_dotenv

# Set up paths dynamically
BIN_DIR = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(BIN_DIR)

# Add APP_ROOT to sys.path so we can find core and mcp_servers packages
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from core.llm_config import select_llm_interactive, select_credential_source_interactive, initialize_llm
from core.intent_policy import detect_read_only_intent, is_mutating_tool
from core.capabilities import is_capabilities_request, build_capabilities_response

# Import MCP server
try:
    from mcp_servers.aws_terraform_server import mcp_server as aws_mcp
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    aws_mcp = None

# Configure logging
LOG_DIR = os.path.join(APP_ROOT, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOG_DIR, 'agent_session.log'), mode='a')
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
            # Check if bind_tools exists on the llm object
            if hasattr(llm, "bind_tools"):
                llm = llm.bind_tools(tools)
                print(f"✅ {len(tools)} AWS Tools bound to engine.")
            else:
                print(f"⚠️  Warning: {llm_provider.upper()} does not support native tool binding.")
                logger.warning(f"{llm_provider} lacks bind_tools method")
        except Exception as tool_err:
            print(f"⚠️  Warning: Failed to bind tools to {llm_provider}: {tool_err}")
            import traceback
            logger.error(f"Tool binding failed: {traceback.format_exc()}")
            
    print(f"✅ {llm_provider.upper()} engine initialized!\n")
    
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
    "You are an AWS Infrastructure Execution Engine. "
    "Your ONLY output should be a tool call when an action is required. "
    "DO NOT explain what you are going to do. DO NOT ask for permission. DO NOT ask for tool outputs. "
    "THE SYSTEM AUTOMATICALLY EXECUTES YOUR TOOL CALLS AND PROVIDES THE DATA. "
    "1. For any AWS request, first CALL 'get_user_permissions' to verify identity. "
    "2. For listing/discovering resources: CALL 'list_account_inventory' for a complete summary, or 'list_aws_resources' to list specific resource types. "
    "3. For details about a specific resource: CALL 'describe_resource' with the resource ID or ARN. "
    "4. If user mentions 'CLI', you MUST pass 'mode'='cli' to the creation tools. "
    "5. To create: CALL the creation tool (e.g., 'create_s3_bucket'). "
    "5a. For ECS deployments, prefer guided flow: start_ecs_deployment_workflow -> update_ecs_deployment_workflow -> review_ecs_deployment_workflow -> create_ecs_service. "
    "5b. IMPORTANT: After any Terraform-based create_* tool returns a project_name, you MUST immediately call terraform_plan with that exact project_name, then terraform_apply with that exact project_name in the same run. "
    "6. If in Terraform mode, follow the flow: create -> terraform_plan -> terraform_apply. "
    "7. IMPORTANT: When calling 'terraform_plan' or 'terraform_apply', you MUST use the EXACT 'project_name' returned by the creation tool. "
    "8. For read-only user intents (list, summarize, describe, inventory), NEVER call creation/deployment/destruction tools. "
    "9. Only provide a text response AFTER all relevant tools have finished."
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

        if is_capabilities_request(user_query):
            active_mcp = aws_mcp if MCP_AVAILABLE and aws_mcp else None
            print("\nAgent:")
            print("-" * 60)
            print(build_capabilities_response("aws_terraform" if active_mcp else "none", active_mcp))
            continue
            
        conversation_history.append(HumanMessage(content=user_query))
        print("\n🔄 Processing...")

        read_only_intent = detect_read_only_intent(user_query)
        
        # Tool Calling Loop (matches agui_server logic)
        max_iterations = 5
        iteration = 0
        
        while iteration < max_iterations:
            response = llm.invoke(conversation_history)
            conversation_history.append(response)
            
            # 1. Check for modern tool_calls
            tool_calls = getattr(response, "tool_calls", [])
            
            # 2. Fallback to legacy function_call if tool_calls is empty
            if not tool_calls and hasattr(response, "additional_kwargs"):
                func_call = response.additional_kwargs.get("function_call")
                if func_call:
                    tool_calls = [{
                        "name": func_call["name"],
                        "args": json.loads(func_call["arguments"]) if isinstance(func_call["arguments"], str) else func_call["arguments"],
                        "id": f"call_{datetime.now().strftime('%M%S')}" # Generate dummy ID
                    }]

            if tool_calls:
                print(f"🛠️  Agent requesting {len(tool_calls)} tool(s)...")
                
                for tool_call in tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    tool_call_id = tool_call.get("id", "legacy_call")
                    
                    print(f"  👉 Executing {tool_name}...")

                    if read_only_intent and is_mutating_tool(tool_name):
                        print(f"  ⛔ Blocked {tool_name}: read-only request")
                        conversation_history.append(ToolMessage(
                            content=json.dumps({
                                "success": False,
                                "error": f"Blocked mutating tool '{tool_name}' because user intent is read-only. Use list_account_inventory, list_aws_resources, or describe_resource."
                            }),
                            tool_call_id=tool_call_id
                        ))
                        continue
                    
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
