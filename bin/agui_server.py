import json
import time
import uuid
import subprocess
from typing import Dict, List, Optional, Any
import warnings
import os
import logging
import sys
from datetime import datetime
import tempfile
from pathlib import Path

# Set up paths dynamically
# This script is in bin/, so go up one level for APP_ROOT
BIN_DIR = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(BIN_DIR)

# Add APP_ROOT to sys.path so we can find core and mcp_servers packages
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

# Suppress urllib3 NotOpenSSLWarning when the system ssl is LibreSSL.
# This is a benign warning on macOS with system LibreSSL and doesn't affect runtime.
try:
    from urllib3.exceptions import NotOpenSSLWarning
    warnings.filterwarnings("ignore", category=NotOpenSSLWarning)
except Exception:
    pass

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from core.llm_config import SUPPORTED_LLMS, initialize_llm
from core.intent_policy import detect_read_only_intent, is_mutating_tool
from core.architecture_parser import ArchitectureParser

# Import MCP server
try:
    from mcp_servers.aws_terraform_server import mcp_server as aws_mcp
    MCP_AVAILABLE = True
    logger_temp = logging.getLogger(__name__)
    logger_temp.info("AWS Terraform MCP Server loaded successfully")
except ImportError as e:
    MCP_AVAILABLE = False
    logger_temp = logging.getLogger(__name__)
    logger_temp.warning(f"MCP Server not available: {e}")
    aws_mcp = None

LOG_DIR = os.path.join(APP_ROOT, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# Configure logging
LOG_FILE = os.path.join(LOG_DIR, 'agui_server.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, mode='a')
    ]
)
logger = logging.getLogger(__name__)

UI_DIR = os.path.join(APP_ROOT, 'ui')

app = FastAPI(title="AWS Infra Agent Bot - AG-UI")
app.mount("/static", StaticFiles(directory=UI_DIR), name="static")

logger.info("=" * 80)
logger.info("AWS Infra Agent Bot - AG-UI Server Starting")
logger.info(f"UI Directory: {UI_DIR}")
logger.info("=" * 80)

conversation_store: Dict[str, List] = {}
llm_cache: Dict[str, object] = {}


class RunRequest(BaseModel):
    message: str
    threadId: str
    provider: str
    model: Optional[str] = None
    credentialSource: Optional[str] = None
    mcpServer: Optional[str] = "none"


@app.get("/")
async def index():
    logger.debug("Serving index.html")
    return FileResponse(f"{UI_DIR}/index.html")


@app.get("/api/models")
async def list_models():
    logger.info("API Request: GET /api/models - Listing available LLM providers")
    providers = []
    for key, config in SUPPORTED_LLMS.items():
        providers.append(
            {
                "key": key,
                "name": config["name"],
                "default_model": config["default_model"],
                "models": [config["default_model"]],
            }
        )
    logger.info(f"Returning {len(providers)} LLM providers")
    return JSONResponse({"providers": providers})


@app.get("/api/mcp/status")
async def mcp_status():
    """Get MCP server status"""
    logger.info("API Request: GET /api/mcp/status")
    
    if not MCP_AVAILABLE or aws_mcp is None:
        return JSONResponse({
            "available": False,
            "message": "MCP Server not available"
        })
    
    try:
        init_result = aws_mcp.initialize()
        return JSONResponse({
            "available": True,
            "initialized": init_result.get("success", False),
            "user_info": init_result.get("user_info", {}),
            "message": init_result.get("message", "")
        })
    except Exception as e:
        logger.error(f"MCP status check failed: {e}")
        return JSONResponse({
            "available": True,
            "initialized": False,
            "error": str(e)
        })


@app.get("/api/mcp/tools")
async def list_mcp_tools():
    """List available MCP tools"""
    logger.info("API Request: GET /api/mcp/tools")
    
    if not MCP_AVAILABLE or aws_mcp is None:
        return JSONResponse({"tools": [], "error": "MCP Server not available"})
    
    try:
        tools = aws_mcp.list_tools()
        logger.info(f"Returning {len(tools)} MCP tools")
        return JSONResponse({"tools": tools})
    except Exception as e:
        logger.error(f"Failed to list MCP tools: {e}")
        return JSONResponse({"tools": [], "error": str(e)})


class MCPToolRequest(BaseModel):
    tool_name: str
    parameters: Dict[str, Any]


@app.post("/api/mcp/execute")
async def execute_mcp_tool(request: MCPToolRequest):
    """Execute an MCP tool"""
    logger.info(f"API Request: POST /api/mcp/execute - Tool: {request.tool_name}")
    logger.info(f"Parameters: {request.parameters}")
    
    if not MCP_AVAILABLE or aws_mcp is None:
        return JSONResponse({
            "success": False,
            "error": "MCP Server not available"
        })
    
    try:
        result = aws_mcp.execute_tool(request.tool_name, request.parameters)
        logger.info(f"MCP tool execution result: {result.get('success', False)}")
        return JSONResponse(result)
    except Exception as e:
        logger.error(f"MCP tool execution failed: {e}", exc_info=True)
        return JSONResponse({
            "success": False,
            "error": str(e)
        })


@app.get("/api/env")
async def get_env():
    """Get non-sensitive environment variables for debugging"""
    logger.info("API Request: GET /api/env")
    env_info = {}
    for k, v in os.environ.items():
        if any(secret in k.upper() for secret in ["KEY", "SECRET", "TOKEN", "PASSWORD"]):
            env_info[k] = "********"
        else:
            env_info[k] = v
    return JSONResponse(env_info)


@app.get("/api/aws/identity")
async def get_aws_identity():
    """Get current AWS identity and check if session is active"""
    logger.info("API Request: GET /api/aws/identity")
    if not MCP_AVAILABLE or aws_mcp is None:
        return JSONResponse({"active": False, "error": "MCP not available"})
    
    try:
        # Re-initialize to catch new credentials
        aws_mcp.rbac.initialize()
        info = aws_mcp.rbac.get_user_info()
        
        if "error" in info:
             return JSONResponse({
                "active": False,
                "error": info["error"],
                "profile": os.environ.get("AWS_PROFILE", "default")
            })

        regions = aws_mcp.rbac.get_allowed_regions()
        return JSONResponse({
            "active": True,
            "account": info.get("account_id"),
            "arn": info.get("user_arn"),
            "regions": regions,
            "profile": os.environ.get("AWS_PROFILE", "default")
        })
    except Exception as e:
        logger.warning(f"Failed to get AWS identity: {e}")
        return JSONResponse({
            "active": False,
            "error": str(e)
        })


@app.post("/api/aws/profile")
async def set_aws_profile(payload: Dict[str, str]):
    """Set the active AWS profile for the server process"""
    profile = payload.get("profile", "default")
    logger.info(f"API Request: POST /api/aws/profile - New Profile: {profile}")
    os.environ["AWS_PROFILE"] = profile
    
    # Force re-initialization of MCP
    if MCP_AVAILABLE and aws_mcp:
        aws_mcp.rbac.initialize()
        
    return JSONResponse({"success": True, "profile": profile})


@app.post("/api/aws/login")
async def trigger_aws_login(payload: Dict[str, str] = None):
    """Trigger 'aws sso login' for the configured profile"""
    profile = (payload or {}).get("profile") or os.environ.get("AWS_PROFILE", "default")
    logger.info(f"API Request: POST /api/aws/login - Profile: {profile}")
    try:
        # Use subprocess to run the login command
        # Removing pipes allows the command to better interact with the OS browser launcher
        process = subprocess.Popen(
            ["aws", "sso", "login", "--profile", profile]
        )
        return JSONResponse({
            "success": True,
            "message": "AWS CLI Login triggered."
        })
    except Exception as e:
        # Fallback to standard configure if SSO login fails
        try:
             # Try simple identity check first
             return JSONResponse({
                "success": False, 
                "error": f"Failed to trigger login: {str(e)}. Please run 'aws configure' in your terminal."
            })
        except:
             pass
        return JSONResponse({"success": False, "error": str(e)})


def get_llm(provider: str, model: Optional[str], credential_source: Optional[str], mcp_server_name: Optional[str] = "none"):
    cache_key = f"{provider}:{model or ''}:{credential_source or 'auto'}:{mcp_server_name or 'none'}"
    if cache_key in llm_cache:
        logger.debug(f"LLM cache hit: {cache_key}")
        return llm_cache[cache_key]

    logger.info(f"Initializing LLM - Provider: {provider}, Model: {model or 'default'}, Credential Source: {credential_source or 'auto'}, MCP: {mcp_server_name}")
    llm = initialize_llm(provider, model=model, preferred_source=credential_source)
    
    # Bind tools if MCP server is selected
    if mcp_server_name == "aws_terraform" and MCP_AVAILABLE and aws_mcp:
        tools = aws_mcp.list_tools()
        # Transform MCP tools to LangChain tools format if necessary
        # For simplicity, we'll assume the LLM supports .bind_tools()
        try:
            # Note: In a real scenario, you'd map these dicts to Tool objects or pass them directly if supported
            # Here we'll pass the tool definitions as dicts which many modern ChatModels support
            llm = llm.bind_tools(tools)
            logger.info(f"Successfully bound {len(tools)} tools from AWS Terraform MCP")
        except Exception as e:
            logger.warning(f"Failed to bind tools to LLM: {e}")

    llm_cache[cache_key] = llm
    logger.info(f"LLM initialized and cached: {cache_key}")
    return llm


def sse_event(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def now_ms() -> int:
    return int(time.time() * 1000)


@app.post("/api/run")
async def run_agent(payload: RunRequest):
    logger.info("=" * 80)
    logger.info("API Request: POST /api/run - New user query received")
    logger.info(f"Provider: {payload.provider}, Model: {payload.model or 'default'}")
    logger.info(f"Credential Source: {payload.credentialSource or 'auto'}")
    logger.info(f"Thread ID: {payload.threadId}")
    logger.info(f"MCP Server: {payload.mcpServer}")
    logger.info(f"Message Length: {len(payload.message)} characters")
    
    if not payload.message.strip():
        logger.warning("Request rejected: Empty message")
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if payload.provider not in SUPPORTED_LLMS:
        logger.error(f"Request rejected: Unsupported provider '{payload.provider}'")
        raise HTTPException(status_code=400, detail="Unsupported provider")

    run_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    thread_id = payload.threadId or str(uuid.uuid4())
    
    logger.info(f"Run ID: {run_id}")
    logger.info(f"Message ID: {message_id}")

    history = conversation_store.setdefault(thread_id, [])
    if not history:
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
            "6. If in Terraform mode, follow the flow: create -> terraform_plan -> terraform_apply. "
            "7. IMPORTANT: When calling 'terraform_plan' or 'terraform_apply', you MUST use the EXACT 'project_name' returned by the creation tool. "
            "8. For read-only user intents (list, summarize, describe, inventory), NEVER call creation/deployment/destruction tools. "
            "9. Only provide a text response AFTER all relevant tools have finished."
        )
        history.append(SystemMessage(content=system_prompt))
        logger.info(f"[{run_id}] System prompt initialized")
    
    # Safety: Only append user message if the last message wasn't already a user message
    if not history or not isinstance(history[-1], HumanMessage):
        history.append(HumanMessage(content=payload.message))
    else:
        # Update the existing last user message if it hasn't been answered yet
        history[-1].content = payload.message
        
    logger.debug(f"Conversation history size: {len(history)} messages")

    read_only_intent = detect_read_only_intent(payload.message)

    def stream():
        try:
            logger.info(f"[{run_id}] Stream started for thread {thread_id}")
            yield sse_event({
                "type": "RUN_STARTED",
                "runId": run_id,
                "threadId": thread_id,
                "timestamp": now_ms(),
            })

            yield sse_event({
                "type": "TEXT_MESSAGE_START",
                "messageId": message_id,
                "role": "assistant",
                "timestamp": now_ms(),
            })
            
            logger.info(f"[{run_id}] Invoking LLM with conversation history")
            
            llm = get_llm(payload.provider, payload.model, payload.credentialSource, payload.mcpServer)
            
            # Check if tools are actually available on this LLM instance
            has_tools = hasattr(llm, "tool_calls") or (hasattr(llm, "bind_tools") and payload.mcpServer != "none")
            logger.info(f"[{run_id}] LLM provider: {payload.provider}, Has Tool Support: {has_tools}")
            
            if payload.provider == "perplexity" and payload.mcpServer != "none":
                yield sse_event({
                    "type": "TEXT_MESSAGE_CONTENT",
                    "messageId": message_id,
                    "delta": "> **Note:** Perplexity (Sonar) may have limited support for dynamic tool calling. If tools aren't being used, try switching to a model like GPT-4o or Gemini.\n\n",
                    "timestamp": now_ms(),
                })
            # Tool calling loop state
            max_iterations = 5
            iteration = 0
            while iteration < max_iterations:
                response = llm.invoke(history)
                history.append(response)
                
                # If there are tool calls, execute them
                if hasattr(response, "tool_calls") and response.tool_calls:
                    logger.info(f"[{run_id}] LLM requested {len(response.tool_calls)} tool calls")
                    
                    for tool_call in response.tool_calls:
                        tool_name = tool_call["name"]
                        tool_args = tool_call["args"]
                        tool_call_id = tool_call["id"]
                        
                        logger.info(f"[{run_id}] Executing tool: {tool_name} with args: {tool_args}")

                        if read_only_intent and is_mutating_tool(tool_name):
                            logger.warning(f"[{run_id}] Blocked mutating tool '{tool_name}' due to read-only user intent")
                            history.append(ToolMessage(
                                content=json.dumps({
                                    "success": False,
                                    "error": f"Blocked mutating tool '{tool_name}' because user intent is read-only. Use list_account_inventory, list_aws_resources, or describe_resource."
                                }),
                                tool_call_id=tool_call_id
                            ))
                            continue
                        
                        # Execute tool via MCP
                        if payload.mcpServer == "aws_terraform" and aws_mcp:
                            try:
                                result = aws_mcp.execute_tool(tool_name, tool_args)
                                logger.info(f"[{run_id}] Tool {tool_name} executed. Success: {result.get('success', False)}")
                                
                                # Stream tool result to UI
                                yield sse_event({
                                    "type": "TOOL_RESULT",
                                    "toolName": tool_name,
                                    "result": result,
                                    "timestamp": now_ms(),
                                })

                                # Add tool result to history
                                history.append(ToolMessage(
                                    content=json.dumps(result),
                                    tool_call_id=tool_call_id
                                ))
                            except Exception as tool_err:
                                logger.error(f"[{run_id}] Tool execution error: {tool_err}")
                                history.append(ToolMessage(
                                    content=json.dumps({"success": False, "error": str(tool_err)}),
                                    tool_call_id=tool_call_id
                                ))
                        else:
                            history.append(ToolMessage(
                                content=json.dumps({"success": False, "error": f"MCP server {payload.mcpServer} not found"}),
                                tool_call_id=tool_call_id
                            ))
                    
                    iteration += 1
                    continue # Re-invoke LLM with tool results
                else:
                    # No more tool calls, we're done
                    break
            
            response_text = response.content if response else ""
            if not response_text.strip():
                if hasattr(response, "tool_calls") and response.tool_calls:
                    response_text = "I have initiated the infrastructure changes as requested."
                else:
                    logger.warning(f"[{run_id}] LLM returned empty response")
                    response_text = "No response generated."
            
            logger.info(f"[{run_id}] Final response generated - Length: {len(response_text)} characters")
            logger.debug(f"[{run_id}] Updated conversation history size: {len(history)} messages")

            chunk_size = 60
            for idx in range(0, len(response_text), chunk_size):
                chunk = response_text[idx : idx + chunk_size]
                yield sse_event({
                    "type": "TEXT_MESSAGE_CONTENT",
                    "messageId": message_id,
                    "delta": chunk,
                    "timestamp": now_ms(),
                })

            yield sse_event({
                "type": "TEXT_MESSAGE_END",
                "messageId": message_id,
                "timestamp": now_ms(),
            })
            
            logger.info(f"[{run_id}] Stream completed successfully")

            yield sse_event({
                "type": "RUN_FINISHED",
                "runId": run_id,
                "threadId": thread_id,
                "timestamp": now_ms(),
            })

        except Exception as exc:
            logger.error(f"[{run_id}] Error during stream execution: {str(exc)}", exc_info=True)
            yield sse_event({
                "type": "RUN_ERROR",
                "runId": run_id,
                "threadId": thread_id,
                "message": str(exc),
                "timestamp": now_ms(),
            })

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/architecture/parse-image")
async def parse_architecture_image(
    file: UploadFile = File(...),
    provider: str = "claude",
    threadId: Optional[str] = None
):
    """
    Parse an AWS architecture image and extract infrastructure components
    
    Supports: PNG, JPG, GIF, WebP
    Uses vision capabilities to analyze the diagram
    """
    logger.info(f"API Request: POST /api/architecture/parse-image - Provider: {provider}")
    
    threadId = threadId or str(uuid.uuid4())
    
    try:
        # Validate file type
        allowed_types = {"image/png", "image/jpeg", "image/gif", "image/webp"}
        if file.content_type not in allowed_types:
            logger.warning(f"Invalid file type: {file.content_type}")
            return JSONResponse(
                {"success": False, "error": f"Invalid file type. Allowed: PNG, JPG, GIF, WebP"},
                status_code=400
            )
        
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        
        try:
            # Initialize LLM if not cached
            if provider not in llm_cache:
                llm_instance = initialize_llm(provider, temperature=0)
                llm_cache[provider] = llm_instance
            
            llm_instance = llm_cache[provider]
            
            # Parse architecture
            parser = ArchitectureParser(llm_provider=provider, llm_instance=llm_instance)
            result = parser.parse_architecture_image(tmp_path)
            
            if result.get("success"):
                logger.info(f"Architecture image parsed successfully for thread {threadId}")
            
            return JSONResponse(result)
        
        finally:
            # Clean up temporary file
            try:
                os.unlink(tmp_path)
            except:
                pass
    
    except Exception as e:
        logger.error(f"Error parsing architecture image: {str(e)}")
        return JSONResponse(
            {"success": False, "error": f"Failed to parse image: {str(e)}"},
            status_code=500
        )


@app.post("/api/architecture/parse-mermaid")
async def parse_mermaid_diagram(
    payload: Dict[str, str],
    provider: str = "claude",
    threadId: Optional[str] = None
):
    """
    Parse a Mermaid diagram string and extract infrastructure components
    
    Mermaid format:
    graph LR
        VPC["VPC"]
        EC2["EC2 Instance"]
        S3["S3 Bucket"]
        VPC --> EC2
        EC2 --> S3
    """
    logger.info(f"API Request: POST /api/architecture/parse-mermaid")
    
    threadId = threadId or str(uuid.uuid4())
    mermaid_content = payload.get("mermaid", "")
    
    if not mermaid_content:
        return JSONResponse(
            {"success": False, "error": "mermaid content is required"},
            status_code=400
        )
    
    try:
        # Parse mermaid
        parser = ArchitectureParser(llm_provider=provider)
        result = parser.parse_mermaid_diagram(mermaid_content)
        
        logger.info(f"Mermaid diagram parsed successfully for thread {threadId}")
        return JSONResponse(result)
    
    except Exception as e:
        logger.error(f"Error parsing mermaid diagram: {str(e)}")
        return JSONResponse(
            {"success": False, "error": f"Failed to parse mermaid: {str(e)}"},
            status_code=500
        )


@app.post("/api/architecture/generate-terraform")
async def generate_terraform_from_architecture(
    payload: Dict[str, Any],
    provider: str = "claude",
    threadId: Optional[str] = None
):
    """
    Generate Terraform code from a parsed architecture
    
    Expects parsed architecture dict from parse_mermaid or parse_image
    """
    logger.info(f"API Request: POST /api/architecture/generate-terraform")
    
    threadId = threadId or str(uuid.uuid4())
    architecture = payload.get("architecture", {})
    
    if not architecture:
        return JSONResponse(
            {"success": False, "error": "architecture dict is required"},
            status_code=400
        )
    
    try:
        # Initialize LLM if not cached
        if provider not in llm_cache:
            llm_instance = initialize_llm(provider, temperature=0)
            llm_cache[provider] = llm_instance
        
        llm_instance = llm_cache[provider]
        
        # Generate Terraform
        parser = ArchitectureParser(llm_provider=provider, llm_instance=llm_instance)
        result = parser.architecture_to_terraform(architecture)
        
        if result.get("success"):
            logger.info(f"Terraform generated successfully for thread {threadId}: {result.get('project_name')}")
        
        return JSONResponse(result)
    
    except Exception as e:
        logger.error(f"Error generating terraform: {str(e)}")
        return JSONResponse(
            {"success": False, "error": f"Failed to generate terraform: {str(e)}"},
            status_code=500
        )


@app.post("/api/architecture/deploy")
async def deploy_architecture(
    payload: Dict[str, Any],
    provider: str = "claude",
    threadId: Optional[str] = None
):
    """
    Generate Terraform from architecture and deploy it using terraform_plan
    
    One-shot deployment endpoint that:
    1. Generates Terraform code
    2. Creates project directory
    3. Runs terraform plan (ready for apply)
    """
    logger.info(f"API Request: POST /api/architecture/deploy")
    
    threadId = threadId or str(uuid.uuid4())
    architecture = payload.get("architecture", {})
    
    if not architecture:
        return JSONResponse(
            {"success": False, "error": "architecture dict is required"},
            status_code=400
        )
    
    try:
        # Initialize LLM
        if provider not in llm_cache:
            llm_instance = initialize_llm(provider, temperature=0)
            llm_cache[provider] = llm_instance
        
        llm_instance = llm_cache[provider]
        
        # Generate Terraform
        parser = ArchitectureParser(llm_provider=provider, llm_instance=llm_instance)
        gen_result = parser.architecture_to_terraform(architecture)
        
        if not gen_result.get("success"):
            return JSONResponse(gen_result, status_code=400)
        
        project_name = gen_result.get("project_name")
        terraform_code = gen_result.get("terraform_code")
        
        # Create project directory and save terraform code
        terraform_workspace = Path(APP_ROOT) / "terraform_workspace"
        terraform_workspace.mkdir(exist_ok=True)
        
        project_dir = terraform_workspace / project_name
        project_dir.mkdir(exist_ok=True)
        
        main_tf = project_dir / "main.tf"
        main_tf.write_text(terraform_code)
        
        logger.info(f"Terraform code saved to {project_dir}/main.tf")
        
        # Initialize terraform and run plan
        if not MCP_AVAILABLE or not aws_mcp:
            return JSONResponse(
                {
                    "success": True,
                    "project_name": project_name,
                    "terraform_code": terraform_code,
                    "message": "Terraform code generated but MCP server not available for planning. Please run terraform_plan manually.",
                    "project_path": str(project_dir)
                }
            )
        
        try:
            # Run terraform init
            init_result = aws_mcp.terraform.init(project_name)
            if not init_result.get("success"):
                return JSONResponse(
                    {
                        "success": False,
                        "error": "Terraform init failed",
                        "details": init_result,
                        "project_name": project_name
                    },
                    status_code=400
                )
            
            # Run terraform plan
            plan_result = aws_mcp.terraform.plan(project_name)
            
            return JSONResponse(
                {
                    "success": plan_result.get("success", False),
                    "project_name": project_name,
                    "terraform_code": terraform_code,
                    "plan_result": plan_result,
                    "message": f"Terraform plan generated for project: {project_name}. Use terraform_apply to deploy.",
                    "project_path": str(project_dir)
                }
            )
        
        except Exception as e:
            logger.error(f"Error running terraform init/plan: {e}")
            return JSONResponse(
                {
                    "success": True,
                    "project_name": project_name,
                    "terraform_code": terraform_code,
                    "message": f"Terraform code generated. Error running plan: {str(e)}. Run terraform_plan manually.",
                    "project_path": str(project_dir),
                    "plan_error": str(e)
                }
            )
    
    except Exception as e:
        logger.error(f"Error in deploy_architecture: {str(e)}")
        return JSONResponse(
            {"success": False, "error": f"Failed to deploy architecture: {str(e)}"},
            status_code=500
        )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "9595"))
    logger.info(f"Starting uvicorn server on http://0.0.0.0:{port}")
    logger.info(f"Reload mode: enabled")
    uvicorn.run("agui_server:app", host="0.0.0.0", port=port, reload=True)
