"""
AWS Lambda handler for LangChain Agent
Converts the interactive CLI agent into a serverless function

Usage:
    Deploy this file with langchain-agent.py, llm_config.py, and requirements.txt to AWS Lambda
    
Example event structure:
{
    "query": "What is the current AWS pricing for EC2?",
    "provider": "perplexity",
    "credential_source": "aws"
}
"""

import json
import os
import logging
import sys

# Configure logging for Lambda
logger = logging.getLogger()
logger.setLevel(logging.INFO)

from typing import Dict, Any, Optional
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

# Set up paths dynamically for Lambda environment or local testing
# This script is in deployment/, so go up one level for APP_ROOT
DEP_DIR = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(DEP_DIR)

# Add APP_ROOT to sys.path so we can find core and mcp_servers packages
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

# Import LLM configuration
try:
    from core.llm_config import initialize_llm, select_llm_interactive
    from core.intent_policy import detect_read_only_intent, is_mutating_tool
    from core.capabilities import (
        is_capabilities_request,
        build_capabilities_response,
        is_audience_request,
        build_audience_response,
    )
except ImportError:
    logger.error("Failed to import core.llm_config")
    raise

# Import MCP server for tool support
try:
    from mcp_servers.aws_terraform_server import mcp_server as aws_mcp
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    aws_mcp = None

def deployment_integrity_check(event: Dict[str, Any]) -> bool:
    """
    Check if this is a real deployment request or just a test/dry-run.
    In production, we expect a 'DEPLOY_REAL_INFRA' flag or env var.
    """
    # 1. Check environment variable (primary)
    if os.getenv("DEPLOY_REAL_INFRA", "false").lower() == "true":
        return True
    
    # 2. Check event flag (for testing/integration)
    if event.get("force_deploy") is True:
        return True
        
    return False

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for the LangChain agent with Tool support
    """
    try:
        # Extract parameters from event
        query = event.get('query')
        provider = event.get('provider', os.getenv('LLM_PROVIDER', 'perplexity'))
        credential_source = event.get('credential_source', 'aws')
        conversation_history = event.get('conversation_history', [])
        is_real_deploy = deployment_integrity_check(event)
        
        # Validate input
        if not query:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing required parameter: query'})
            }

        if is_audience_request(query):
            response_text = build_audience_response()
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'is_real_deploy': False,
                    'tool_usage': False
                }),
                'response': response_text,
                'conversation_history': conversation_history
            }

        if is_capabilities_request(query):
            active_mcp = aws_mcp if MCP_AVAILABLE and aws_mcp else None
            response_text = build_capabilities_response("aws_terraform" if active_mcp else "none", active_mcp, query)
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'is_real_deploy': False,
                    'tool_usage': False
                }),
                'response': response_text,
                'conversation_history': conversation_history
            }
        
        logger.info(f"Processing query. Real Deploy: {is_real_deploy}")
        
        # Initialize LLM
        llm = initialize_llm(provider, temperature=0, preferred_source=credential_source)
        
        # Bind tools if available
        if MCP_AVAILABLE and aws_mcp:
            tools = aws_mcp.list_tools()
            llm = llm.bind_tools(tools)
            logger.info(f"Bound {len(tools)} tools to LLM")
        
        # Prepare system prompt
        system_prompt = (
            "You are a strict AWS Infrastructure Provisioning Agent. "
            "You MUST use tools for any AWS operations. "
            f"Deployment Integrity: {'REAL_MODE' if is_real_deploy else 'DRY_RUN_MODE'}. "
            "If in 'DRY_RUN_MODE', inform the user that infrastructure will not be actually deployed. "
            "For ECS deployments, use guided tool chain start_ecs_deployment_workflow -> update_ecs_deployment_workflow -> review_ecs_deployment_workflow -> create_ecs_service. "
            "After any Terraform-based create_* tool returns project_name, immediately call terraform_plan and terraform_apply with that exact project_name. "
            "For read-only intents (list, summarize, describe, inventory), NEVER call creation/deployment/destruction tools."
        )
        
        messages = [HumanMessage(content=system_prompt if not conversation_history else "")]
        # ... (rest of message conversion from original)
        if conversation_history:
            for msg in conversation_history:
                if msg.get('role') == 'user':
                    messages.append(HumanMessage(content=msg.get('content')))
                elif msg.get('role') == 'assistant':
                    messages.append(AIMessage(content=msg.get('content')))
        
        messages.append(HumanMessage(content=query))
        read_only_intent = detect_read_only_intent(query)
        
        # Tool execution loop
        max_iterations = 5
        iteration = 0
        final_response = ""
        
        while iteration < max_iterations:
            response = llm.invoke(messages)
            messages.append(response)
            
            if hasattr(response, "tool_calls") and response.tool_calls:
                logger.info(f"Iteration {iteration}: Handling {len(response.tool_calls)} tool calls")
                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    tool_call_id = tool_call["id"]
                    tool_is_mutating = is_mutating_tool(tool_name)
                    
                    # Logic to block actual apply if not real deploy
                    if read_only_intent and tool_is_mutating:
                        result = {
                            "success": False,
                            "error": f"Blocked mutating tool '{tool_name}' because user intent is read-only. Use list_account_inventory, list_aws_resources, or describe_resource."
                        }
                    elif tool_name == "terraform_apply" and not is_real_deploy:
                        result = {"success": False, "error": "DRY_RUN_MODE: Actual deployment blocked. Please set DEPLOY_REAL_INFRA=true to proceed."}
                    elif MCP_AVAILABLE and aws_mcp:
                        result = aws_mcp.execute_tool(tool_name, tool_args)
                    else:
                        result = {"error": "MCP tools not available"}
                        
                    messages.append(ToolMessage(content=json.dumps(result), tool_call_id=tool_call_id))
                iteration += 1
            else:
                final_response = response.content
                break
        
        # Prepare history for return
        updated_history = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                updated_history.append({'role': 'user', 'content': msg.content})
            elif isinstance(msg, AIMessage):
                updated_history.append({'role': 'assistant', 'content': msg.content})
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'is_real_deploy': is_real_deploy,
                'tool_usage': iteration > 0
            }),
            'response': final_response,
            'conversation_history': updated_history
        }
    
    except Exception as e:
        logger.error(f"Unhandled error: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Internal server error: {str(e)}'}),
            'response': None
        }


# Lambda handler for direct invocation (synchronous)
def sync_invoke(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Synchronous Lambda invocation"""
    return lambda_handler(event, context)


# Optional: Layer handler for scheduled tasks
def scheduled_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handler for EventBridge scheduled invocations
    Useful for periodic monitoring or report generation
    """
    logger.info(f"Scheduled invocation triggered at {event.get('time')}")
    
    default_query = "What are the latest AWS infrastructure updates?"
    
    invoke_event = {
        'query': default_query,
        'provider': os.getenv('LLM_PROVIDER', 'perplexity'),
        'credential_source': 'aws'
    }
    
    return lambda_handler(invoke_event, context)


if __name__ == "__main__":
    # Local testing
    test_event = {
        'query': 'What is Amazon EC2?',
        'provider': 'perplexity',
        'credential_source': 'local'
    }
    
    class MockContext:
        request_id = "test-request-id"
        function_name = "langchain-agent-test"
    
    result = lambda_handler(test_event, MockContext())
    print(json.dumps(result, indent=2))
