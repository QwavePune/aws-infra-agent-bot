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

# Suppress urllib3 NotOpenSSLWarning when the system ssl is LibreSSL.
# This is a benign warning on macOS with system LibreSSL and doesn't affect runtime.
try:
    from urllib3.exceptions import NotOpenSSLWarning

    warnings.filterwarnings("ignore", category=NotOpenSSLWarning)
except Exception:
    # If urllib3 isn't available yet or the exception class isn't present,
    # skip silencing the warning to avoid import errors.
    pass

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
 

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from llm_config import SUPPORTED_LLMS, initialize_llm

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

APP_ROOT = "/Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot"

# Configure logging
LOG_FILE = os.path.join(APP_ROOT, 'agui-server.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, mode='a')
    ]
)
logger = logging.getLogger(__name__)

UI_DIR = f"{APP_ROOT}/ui"

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
        regions = aws_mcp.rbac.get_allowed_regions()
        return JSONResponse({
            "active": True,
            "account": info.get("account_id"),
            "arn": info.get("user_arn"),
            "regions": regions
        })
    except Exception as e:
        logger.warning(f"Failed to get AWS identity: {e}")
        return JSONResponse({
            "active": False,
            "error": str(e)
        })


@app.post("/api/aws/login")
async def trigger_aws_login():
    """Trigger 'aws sso login' or standard login"""
    logger.info("API Request: POST /api/aws/login")
    try:
        # Use subprocess to run the login command
        # Removing pipes allows the command to better interact with the OS browser launcher
        process = subprocess.Popen(
            ["aws", "sso", "login"]
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
            "You are a strict AWS Infrastructure Provisioning Agent. "
            "CRITICAL: You MUST use the provided MCP tools for ANY infrastructure operation. "
            "NEVER hallucinate or simulate a successful deployment. If you encounter an error or lack permissions, report it honestly. "
            "To build infrastructure: 1. Generate the project/config 2. Run terraform_plan 3. Run terraform_apply. "
            "If a user says 'apply' or 'execute', you MUST call the terraform_apply tool with the correct project name. "
            "Always report the real output from the tools. If you need AWS credentials, remind the user to click 'CLI Login'."
        )
        history.append(SystemMessage(content=system_prompt))
    
    # Safety: Only append user message if the last message wasn't already a user message
    if not history or not isinstance(history[-1], HumanMessage):
        history.append(HumanMessage(content=payload.message))
    else:
        # Update the existing last user message if it hasn't been answered yet
        history[-1].content = payload.message
        
    logger.debug(f"Conversation history size: {len(history)} messages")

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
            
            # Simple tool calling loop
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


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    logger.info(f"Starting uvicorn server on http://0.0.0.0:{port}")
    logger.info(f"Reload mode: enabled")
    uvicorn.run("agui_server:app", host="0.0.0.0", port=port, reload=True)
