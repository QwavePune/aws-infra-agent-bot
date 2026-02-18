import json
import logging
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

# Set up paths dynamically
BIN_DIR = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(BIN_DIR)

# Add APP_ROOT to sys.path so we can find core and mcp_servers packages
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from core.agent_protocol import EXECUTION_SYSTEM_PROMPT, build_followup_message, extract_tool_calls
from core.architecture_parser import ArchitectureParser
from core.capabilities import (
    build_capabilities_response,
    is_capabilities_request,
    is_audience_request,
    build_audience_response,
)
from core.intent_policy import detect_read_only_intent, is_mutating_tool
from core.llm_config import (
    SUPPORTED_LLMS,
    initialize_llm,
    select_credential_source_interactive,
    select_llm_interactive,
)
from core.workflow_logger import setup_workflow_logger, workflow_event

# Import MCP server
try:
    from mcp_servers.aws_terraform_server import mcp_server as aws_mcp

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    aws_mcp = None

# Configure logging
LOG_DIR = os.path.join(APP_ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOG_DIR, "agent_session.log"), mode="a"),
    ],
)
logger = logging.getLogger(__name__)
workflow_logger = setup_workflow_logger(APP_ROOT, "cli")

# Load environment variables
load_dotenv()


def mask_env() -> Dict[str, str]:
    env_info = {}
    for key, value in os.environ.items():
        if any(secret in key.upper() for secret in ["KEY", "SECRET", "TOKEN", "PASSWORD"]):
            env_info[key] = "********"
        else:
            env_info[key] = value
    return env_info


def bind_mcp_tools(llm: Any, llm_provider: str) -> Any:
    if not (MCP_AVAILABLE and aws_mcp):
        return llm

    tools = aws_mcp.list_tools()
    if hasattr(llm, "bind_tools"):
        try:
            llm = llm.bind_tools(tools)
            print(f"✅ {len(tools)} AWS tools bound to {llm_provider.upper()}.")
        except Exception as tool_err:
            print(f"⚠️  Failed to bind tools to {llm_provider}: {tool_err}")
            logger.warning("Tool binding failed: %s", tool_err, exc_info=True)
    else:
        print(f"⚠️  {llm_provider.upper()} does not support native tool binding.")
    return llm


def initialize_session_llm(
    llm_provider: str,
    credential_source: Optional[str],
    model: Optional[str] = None,
) -> Any:
    print(f"\n[INFO] Initializing {llm_provider.upper()}...")
    llm = initialize_llm(llm_provider, model=model, temperature=0, preferred_source=credential_source)
    llm = bind_mcp_tools(llm, llm_provider)
    print(f"✅ {llm_provider.upper()} engine initialized.\n")
    return llm


def print_models() -> None:
    print("\nAvailable providers/models:")
    for key, config in SUPPORTED_LLMS.items():
        print(f"- {key}: {config.get('name')} (default: {config.get('default_model')})")


def print_aws_identity() -> None:
    if not (MCP_AVAILABLE and aws_mcp):
        print("❌ MCP server is not available.")
        return

    aws_mcp.rbac.initialize()
    info = aws_mcp.rbac.get_user_info()
    if "error" in info:
        print(f"❌ AWS identity unavailable: {info['error']}")
        print(f"Profile: {os.environ.get('AWS_PROFILE', 'default')}")
        return

    regions = aws_mcp.rbac.get_allowed_regions()
    print("\nAWS Identity")
    print(f"- Profile: {os.environ.get('AWS_PROFILE', 'default')}")
    print(f"- Account: {info.get('account_id')}")
    print(f"- ARN: {info.get('user_arn')}")
    print(f"- Regions: {len(regions)} available")


def print_mcp_status() -> None:
    if not (MCP_AVAILABLE and aws_mcp):
        print("MCP available: False")
        return

    init_result = aws_mcp.initialize()
    print(f"MCP available: True")
    print(f"Initialized: {init_result.get('success', False)}")
    if init_result.get("user_info"):
        print(f"User: {init_result['user_info'].get('user_arn', 'unknown')}")
    if init_result.get("message"):
        print(f"Message: {init_result['message']}")


def print_mcp_tools() -> None:
    if not (MCP_AVAILABLE and aws_mcp):
        print("❌ MCP server is not available.")
        return

    tools = aws_mcp.list_tools()
    print(f"\nMCP tools ({len(tools)}):")
    for tool in tools:
        print(f"- {tool.get('name')}: {tool.get('description', '')}")


def run_architecture_parse_image(image_path: str, llm_provider: str, llm: Any) -> None:
    path = Path(image_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        print(f"❌ File not found: {path}")
        return

    parser = ArchitectureParser(llm_provider=llm_provider, llm_instance=llm)
    result = parser.parse_architecture_image(str(path))
    print(json.dumps(result, indent=2, default=str))


def run_architecture_parse_mermaid(mermaid_path: str) -> None:
    path = Path(mermaid_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        print(f"❌ File not found: {path}")
        return

    parser = ArchitectureParser()
    result = parser.parse_mermaid_diagram(path.read_text())
    print(json.dumps(result, indent=2, default=str))


def run_architecture_generate(terraform_input_path: str, llm_provider: str, llm: Any) -> None:
    path = Path(terraform_input_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        print(f"❌ File not found: {path}")
        return

    architecture = json.loads(path.read_text())
    parser = ArchitectureParser(llm_provider=llm_provider, llm_instance=llm)
    result = parser.architecture_to_terraform(architecture)
    print(json.dumps(result, indent=2, default=str))


def run_architecture_deploy(terraform_input_path: str, llm_provider: str, llm: Any) -> None:
    path = Path(terraform_input_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        print(f"❌ File not found: {path}")
        return

    architecture = json.loads(path.read_text())
    parser = ArchitectureParser(llm_provider=llm_provider, llm_instance=llm)
    gen_result = parser.architecture_to_terraform(architecture)
    if not gen_result.get("success"):
        print(json.dumps(gen_result, indent=2, default=str))
        return

    project_name = gen_result.get("project_name")
    terraform_code = gen_result.get("terraform_code")

    terraform_workspace = Path(APP_ROOT) / "terraform_workspace"
    terraform_workspace.mkdir(exist_ok=True)
    project_dir = terraform_workspace / project_name
    project_dir.mkdir(exist_ok=True)
    (project_dir / "main.tf").write_text(terraform_code)

    if not (MCP_AVAILABLE and aws_mcp):
        print(
            json.dumps(
                {
                    "success": True,
                    "project_name": project_name,
                    "project_path": str(project_dir),
                    "message": "Terraform generated. MCP unavailable for init/plan.",
                },
                indent=2,
            )
        )
        return

    init_result = aws_mcp.terraform.init(project_name)
    if not init_result.get("success"):
        print(json.dumps({"success": False, "init_result": init_result}, indent=2, default=str))
        return

    plan_result = aws_mcp.terraform.plan(project_name)
    print(
        json.dumps(
            {
                "success": plan_result.get("success", False),
                "project_name": project_name,
                "project_path": str(project_dir),
                "plan_result": plan_result,
                "message": "Run terraform_apply with the same project_name to deploy.",
            },
            indent=2,
            default=str,
        )
    )


def print_help() -> None:
    print("\nCommands:")
    print("- help")
    print("- clear")
    print("- quit | exit | q | x")
    print("- /models")
    print("- /mcp-status")
    print("- /mcp-tools")
    print("- /mcp-exec <tool_name> <json_params>")
    print("- /aws-identity")
    print("- /aws-profile <profile_name>")
    print("- /aws-login [profile_name]")
    print("- /provider [provider_key] [model]")
    print("- /credential-source [source]")
    print("- /env")
    print("- /arch-parse-image <image_path>")
    print("- /arch-parse-mermaid <mermaid_file_path>")
    print("- /arch-generate-terraform <architecture_json_path>")
    print("- /arch-deploy <architecture_json_path>")


def handle_cli_command(
    user_query: str,
    state: Dict[str, Any],
    conversation_history: list,
) -> bool:
    if not user_query.startswith("/"):
        return False

    try:
        parts = shlex.split(user_query)
    except ValueError as e:
        print(f"❌ Invalid command syntax: {e}")
        return True

    command = parts[0].lower()
    args = parts[1:]

    try:
        if command == "/models":
            print_models()
            return True

        if command == "/mcp-status":
            print_mcp_status()
            return True

        if command == "/mcp-tools":
            print_mcp_tools()
            return True

        if command == "/mcp-exec":
            if len(args) < 2:
                print("Usage: /mcp-exec <tool_name> <json_params>")
                return True
            if not (MCP_AVAILABLE and aws_mcp):
                print("❌ MCP server is not available.")
                return True
            tool_name = args[0]
            tool_params = json.loads(" ".join(args[1:]))
            result = aws_mcp.execute_tool(tool_name, tool_params)
            print(json.dumps(result, indent=2, default=str))
            return True

        if command == "/aws-identity":
            print_aws_identity()
            return True

        if command == "/aws-profile":
            if not args:
                print(f"Current profile: {os.environ.get('AWS_PROFILE', 'default')}")
                return True
            os.environ["AWS_PROFILE"] = args[0]
            print(f"✅ AWS_PROFILE set to: {args[0]}")
            if MCP_AVAILABLE and aws_mcp:
                aws_mcp.rbac.initialize()
            return True

        if command == "/aws-login":
            profile = args[0] if args else os.environ.get("AWS_PROFILE", "default")
            try:
                subprocess.Popen(["aws", "sso", "login", "--profile", profile])
                print(f"✅ Triggered aws sso login for profile: {profile}")
            except Exception as e:
                print(f"❌ Failed to trigger AWS login: {e}")
            return True

        if command == "/provider":
            if not args:
                print(f"Current provider: {state['provider']}")
                print(f"Current model: {state.get('model') or 'default'}")
                return True
            provider = args[0].lower()
            model = args[1] if len(args) > 1 else None
            state["llm"] = initialize_session_llm(provider, state.get("credential_source"), model=model)
            state["provider"] = provider
            state["model"] = model
            print("✅ Provider/model updated.")
            return True

        if command == "/credential-source":
            if not args:
                print(f"Current credential source: {state.get('credential_source') or 'auto'}")
                return True
            source = args[0]
            state["llm"] = initialize_session_llm(state["provider"], source, model=state.get("model"))
            state["credential_source"] = source
            print("✅ Credential source updated.")
            return True

        if command == "/env":
            print(json.dumps(mask_env(), indent=2, default=str))
            return True

        if command == "/arch-parse-image":
            if not args:
                print("Usage: /arch-parse-image <image_path>")
                return True
            run_architecture_parse_image(args[0], state["provider"], state["llm"])
            return True

        if command == "/arch-parse-mermaid":
            if not args:
                print("Usage: /arch-parse-mermaid <mermaid_file_path>")
                return True
            run_architecture_parse_mermaid(args[0])
            return True

        if command == "/arch-generate-terraform":
            if not args:
                print("Usage: /arch-generate-terraform <architecture_json_path>")
                return True
            run_architecture_generate(args[0], state["provider"], state["llm"])
            return True

        if command == "/arch-deploy":
            if not args:
                print("Usage: /arch-deploy <architecture_json_path>")
                return True
            run_architecture_deploy(args[0], state["provider"], state["llm"])
            return True

        print(f"❌ Unknown command: {command}. Type 'help' for commands.")
        return True

    except Exception as e:
        print(f"❌ Command failed: {e}")
        logger.error("Command failure: %s", e, exc_info=True)
        return True


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
change_profile = input(f"Current AWS Profile: {current_profile}. Change it? (y/N): ").strip().lower()
if change_profile == "y":
    new_profile = input("Enter AWS Profile name: ").strip()
    if new_profile:
        os.environ["AWS_PROFILE"] = new_profile
        current_profile = new_profile
        print(f"✅ AWS_PROFILE set to: {current_profile}")

# 2. LLM Provider Selection
llm_provider = os.getenv("LLM_PROVIDER", "").lower()
if not llm_provider:
    llm_provider = select_llm_interactive()

try:
    credential_source = select_credential_source_interactive()
    llm = initialize_session_llm(llm_provider, credential_source)

    if MCP_AVAILABLE and aws_mcp:
        print("Checking AWS Identity...")
        print_aws_identity()
except Exception as e:
    print(f"\n❌ Initialization Error: {e}")
    logger.error("Failed to initialize: %s", str(e), exc_info=True)
    sys.exit(1)

state: Dict[str, Any] = {
    "provider": llm_provider,
    "model": None,
    "credential_source": credential_source,
    "llm": llm,
}

# Interactive query loop
print("\n" + "=" * 60)
print("Conversational Agent - Type 'help' for commands")
print("=" * 60)

system_prompt = EXECUTION_SYSTEM_PROMPT
conversation_history = [SystemMessage(content=system_prompt)]

while True:
    try:
        user_query = input("\nYou: ").strip()

        if user_query.lower() in ["quit", "exit", "q", "x"]:
            print("\n👋 Goodbye!")
            break

        if user_query.lower() == "help":
            print_help()
            continue

        if user_query.lower() == "clear":
            conversation_history = [SystemMessage(content=system_prompt)]
            print("✅ Conversation history cleared")
            continue

        if not user_query:
            continue

        run_id = os.urandom(8).hex()
        workflow_event(
            workflow_logger,
            "query_received",
            source="cli",
            run_id=run_id,
            provider=state.get("provider"),
            model=state.get("model") or "default",
            metadata={"class": "CLI", "method": "interactive_loop"},
            user_query=user_query,
        )

        if handle_cli_command(user_query, state, conversation_history):
            workflow_event(
                workflow_logger,
                "command_handled",
                source="cli",
                run_id=run_id,
                metadata={"class": "CLI", "method": "handle_cli_command"},
            )
            continue

        if is_audience_request(user_query):
            print("\nAgent:")
            print("-" * 60)
            print(build_audience_response())
            workflow_event(
                workflow_logger,
                "audience_response_generated",
                source="cli",
                run_id=run_id,
                metadata={"class": "CLI", "method": "build_audience_response"},
            )
            continue

        if is_capabilities_request(user_query):
            active_mcp = aws_mcp if MCP_AVAILABLE and aws_mcp else None
            print("\nAgent:")
            print("-" * 60)
            print(build_capabilities_response("aws_terraform" if active_mcp else "none", active_mcp, user_query))
            workflow_event(
                workflow_logger,
                "capabilities_response_generated",
                source="cli",
                run_id=run_id,
                metadata={"class": "CLI", "method": "build_capabilities_response"},
            )
            continue

        conversation_history.append(HumanMessage(content=user_query))
        print("\n🔄 Processing...")

        read_only_intent = detect_read_only_intent(user_query)

        # Tool Calling Loop (matches agui_server logic)
        max_iterations = 5
        iteration = 0
        forced_followup_text = ""

        while iteration < max_iterations:
            workflow_event(
                workflow_logger,
                "llm_invocation_started",
                source="cli",
                run_id=run_id,
                iteration=iteration + 1,
                metadata={"class": "LLM", "method": "invoke"},
            )
            response = state["llm"].invoke(conversation_history)
            conversation_history.append(response)

            tool_calls = extract_tool_calls(response)

            if tool_calls:
                print(f"🛠️  Agent requesting {len(tool_calls)} tool(s)...")
                workflow_event(
                    workflow_logger,
                    "tool_calls_requested",
                    source="cli",
                    run_id=run_id,
                    iteration=iteration + 1,
                    tool_count=len(tool_calls),
                    metadata={"class": "LLM", "method": "invoke"},
                )

                for tool_call in tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    tool_call_id = tool_call.get("id", "legacy_call")

                    print(f"  👉 Executing {tool_name}...")
                    workflow_event(
                        workflow_logger,
                        "tool_execution_started",
                        source="cli",
                        run_id=run_id,
                        tool_name=tool_name,
                        tool_call_id=tool_call_id,
                        tool_args=tool_args,
                        metadata={"class": "MCPAWSManagerServer", "method": "execute_tool"},
                    )

                    if read_only_intent and is_mutating_tool(tool_name):
                        print(f"  ⛔ Blocked {tool_name}: read-only request")
                        workflow_event(
                            workflow_logger,
                            "tool_execution_blocked",
                            source="cli",
                            run_id=run_id,
                            tool_name=tool_name,
                            reason="read_only_intent",
                            metadata={"class": "IntentPolicy", "method": "is_mutating_tool"},
                        )
                        conversation_history.append(
                            ToolMessage(
                                content=json.dumps(
                                    {
                                        "success": False,
                                        "error": f"Blocked mutating tool '{tool_name}' because user intent is read-only. Use list_account_inventory, list_aws_resources, or describe_resource.",
                                    }
                                ),
                                tool_call_id=tool_call_id,
                            )
                        )
                        continue

                    if MCP_AVAILABLE and aws_mcp:
                        try:
                            result = aws_mcp.execute_tool(tool_name, tool_args)
                            followup_text = build_followup_message(tool_name, result)
                            if followup_text:
                                forced_followup_text = followup_text
                            workflow_event(
                                workflow_logger,
                                "tool_execution_completed",
                                source="cli",
                                run_id=run_id,
                                tool_name=tool_name,
                                tool_call_id=tool_call_id,
                                success=result.get("success", False),
                                tool_result=result,
                                metadata={"class": "MCPAWSManagerServer", "method": "execute_tool"},
                            )
                            status = "✅" if result.get("success", False) else "❌"
                            print(
                                f"  {status} Result: {str(result.get('message', result.get('error', 'Success')))[:200]}..."
                            )

                            conversation_history.append(
                                ToolMessage(content=json.dumps(result), tool_call_id=tool_call_id)
                            )
                        except Exception as tool_err:
                            print(f"  ❌ Tool Error: {tool_err}")
                            workflow_event(
                                workflow_logger,
                                "tool_execution_failed",
                                source="cli",
                                run_id=run_id,
                                tool_name=tool_name,
                                tool_call_id=tool_call_id,
                                error=str(tool_err),
                                metadata={"class": "MCPAWSManagerServer", "method": "execute_tool"},
                            )
                            conversation_history.append(
                                ToolMessage(
                                    content=json.dumps({"success": False, "error": str(tool_err)}),
                                    tool_call_id=tool_call_id,
                                )
                            )
                    else:
                        conversation_history.append(
                            ToolMessage(
                                content=json.dumps({"success": False, "error": "MCP server not available"}),
                                tool_call_id=tool_call_id,
                            )
                        )

                iteration += 1
                continue

            print("\nAgent:")
            print("-" * 60)
            if forced_followup_text:
                print(forced_followup_text)
            else:
                print(response.content)
            workflow_event(
                workflow_logger,
                "run_finished",
                source="cli",
                run_id=run_id,
                response_text=forced_followup_text or str(response.content),
                metadata={"class": "CLI", "method": "interactive_loop"},
            )
            break

    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
        break
    except Exception as e:
        print(f"\n❌ Error: {e}")
        logger.error("Loop error: %s", str(e), exc_info=True)
        workflow_event(
            workflow_logger,
            "run_failed",
            source="cli",
            error=str(e),
            metadata={"class": "CLI", "method": "interactive_loop"},
        )
