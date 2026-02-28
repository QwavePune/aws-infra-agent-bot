import json
import time
import uuid
import subprocess
import csv
import io
import glob
import threading
import configparser
import shutil
import hashlib
from typing import Dict, List, Optional, Any, Iterable, Tuple
import warnings
import os
import logging
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone
import boto3

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

from fastapi import FastAPI, HTTPException, UploadFile, File, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from core.llm_config import SUPPORTED_LLMS, initialize_llm
from core.capabilities import (
    is_capabilities_request,
    build_capabilities_response,
    is_audience_request,
    build_audience_response,
)
from core.intent_policy import detect_read_only_intent, is_mutating_tool
from core.architecture_parser import ArchitectureParser
from core.agent_protocol import EXECUTION_SYSTEM_PROMPT, extract_tool_calls, build_followup_message
from core.workflow_logger import setup_workflow_logger, workflow_event

# Import MCP servers
try:
    from mcp_servers.aws_terraform_server import mcp_server as aws_mcp
    AWS_MCP_AVAILABLE = True
    logger_temp = logging.getLogger(__name__)
    logger_temp.info("AWS Terraform MCP Server loaded successfully")
except ImportError as e:
    AWS_MCP_AVAILABLE = False
    logger_temp = logging.getLogger(__name__)
    logger_temp.warning(f"AWS MCP Server not available: {e}")
    aws_mcp = None

try:
    from mcp_servers.azure_terraform_server import mcp_server as azure_mcp
    AZURE_MCP_AVAILABLE = True
    logger_temp = logging.getLogger(__name__)
    logger_temp.info("Azure Terraform MCP Server loaded successfully")
except ImportError as e:
    AZURE_MCP_AVAILABLE = False
    logger_temp = logging.getLogger(__name__)
    logger_temp.warning(f"Azure MCP Server not available: {e}")
    azure_mcp = None

MCP_AVAILABLE = AWS_MCP_AVAILABLE or AZURE_MCP_AVAILABLE

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
workflow_logger = setup_workflow_logger(APP_ROOT, "agui")

UI_DIR = os.path.join(APP_ROOT, 'ui')
WORKFLOW_LOG_DIR = os.path.join(APP_ROOT, "logs", "workflow_execution_log")

app = FastAPI(title="AWS Infra Agent Bot - AG-UI")
app.mount("/static", StaticFiles(directory=UI_DIR), name="static")

logger.info("=" * 80)
logger.info("AWS Infra Agent Bot - AG-UI Server Starting")
logger.info(f"UI Directory: {UI_DIR}")
logger.info("=" * 80)

conversation_store: Dict[str, List] = {}
llm_cache: Dict[str, object] = {}
maker_checker_lock = threading.Lock()
maker_checker_requests: Dict[str, Dict[str, Any]] = {}
aws_login_lock = threading.Lock()
aws_login_jobs: Dict[str, Dict[str, Any]] = {}
aws_login_latest_id: Optional[str] = None
client_profile_lock = threading.Lock()
client_active_profiles: Dict[str, str] = {}

os.environ.setdefault("AWS_PROFILE", "default")
MAKER_CHECKER_CONFIG_PATH = os.path.join(LOG_DIR, "maker_checker_roles.json")
maker_checker_roles_lock = threading.Lock()
maker_checker_roles: Dict[str, List[str]] = {"checker_profiles": [], "maker_profiles": []}


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_profile_list(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    values = [v.strip() for v in str(raw).split(",")]
    return [v for v in values if v]


def _normalize_profiles(values: Optional[Iterable[str]]) -> List[str]:
    seen: set[str] = set()
    normalized: List[str] = []
    for item in values or []:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _default_checker_profiles() -> List[str]:
    env_many = _parse_profile_list(os.environ.get("MAKER_CHECKER_CHECKER_PROFILES"))
    env_one = _parse_profile_list(os.environ.get("MAKER_CHECKER_CHECKER_PROFILE"))
    combined = _normalize_profiles(env_many + env_one)
    if combined:
        return combined
    return [os.environ.get("AWS_PROFILE", "default")]


def _load_maker_checker_roles() -> Dict[str, List[str]]:
    checkers: List[str] = []
    makers: List[str] = []
    try:
        if os.path.exists(MAKER_CHECKER_CONFIG_PATH):
            with open(MAKER_CHECKER_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            checkers = _normalize_profiles(data.get("checker_profiles", []))
            makers = _normalize_profiles(data.get("maker_profiles", []))
    except Exception as e:
        logger.warning(f"Failed to read maker-checker config file '{MAKER_CHECKER_CONFIG_PATH}': {e}")

    if not checkers:
        checkers = _default_checker_profiles()
    return {"checker_profiles": checkers, "maker_profiles": makers}


def _save_maker_checker_roles(config: Dict[str, List[str]]) -> None:
    payload = {
        "checker_profiles": _normalize_profiles(config.get("checker_profiles", [])),
        "maker_profiles": _normalize_profiles(config.get("maker_profiles", [])),
        "updated_at": _utc_iso_now(),
    }
    with open(MAKER_CHECKER_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _checker_profiles() -> List[str]:
    with maker_checker_roles_lock:
        values = list(maker_checker_roles.get("checker_profiles", []))
    return _normalize_profiles(values) or _default_checker_profiles()


def _maker_profiles() -> List[str]:
    with maker_checker_roles_lock:
        values = list(maker_checker_roles.get("maker_profiles", []))
    return _normalize_profiles(values)


def _primary_checker_profile() -> str:
    checkers = _checker_profiles()
    return checkers[0] if checkers else ""


def _is_checker_profile(profile: str) -> bool:
    return str(profile or "").strip() in set(_checker_profiles())


def _is_maker_profile(profile: str) -> bool:
    p = str(profile or "").strip()
    if not p:
        return False
    makers = set(_maker_profiles())
    if makers:
        return p in makers
    return not _is_checker_profile(p)


def _client_key_from_request(request: Optional[Request]) -> str:
    if not request:
        return "global"
    explicit = (request.headers.get("x-agui-client-id") or "").strip()
    if explicit:
        return explicit
    ua = (request.headers.get("user-agent") or "").strip()
    if ua:
        return f"ua:{hashlib.sha1(ua.encode('utf-8')).hexdigest()[:16]}"
    host = (request.client.host if request and request.client else "unknown")
    return f"ip:{host}"


def _current_profile(request: Optional[Request] = None) -> str:
    if request is not None:
        key = _client_key_from_request(request)
        with client_profile_lock:
            profile = client_active_profiles.get(key)
        if profile:
            return profile
    return os.environ.get("AWS_PROFILE", "default")


def _set_client_profile(profile: str, request: Optional[Request] = None, client_key: Optional[str] = None) -> None:
    key = client_key or _client_key_from_request(request)
    with client_profile_lock:
        client_active_profiles[key] = profile


def _activate_profile(profile: str) -> None:
    os.environ["AWS_PROFILE"] = profile
    os.environ["AWS_DEFAULT_PROFILE"] = profile
    for env_key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        os.environ.pop(env_key, None)
    _reset_aws_context()


def _extract_user_name_from_arn(arn: str) -> str:
    if not arn:
        return "unknown"
    if ":assumed-role/" in arn:
        tail = arn.split(":assumed-role/", 1)[1]
        parts = tail.split("/")
        if len(parts) >= 2:
            return parts[1]
    if ":user/" in arn:
        return arn.rsplit("/", 1)[-1]
    if arn.endswith(":root"):
        return "root"
    return arn.rsplit("/", 1)[-1]


def _reset_aws_context() -> None:
    """Reset cached boto context so profile changes are picked up reliably."""
    try:
        boto3.DEFAULT_SESSION = None
    except Exception:
        pass
    if MCP_AVAILABLE and aws_mcp:
        aws_mcp.rbac.sts_client = None
        aws_mcp.rbac.iam_client = None
        aws_mcp.rbac.identity = None


def _list_aws_profiles() -> List[str]:
    profiles: set[str] = set()
    aws_config = Path.home() / ".aws" / "config"
    aws_credentials = Path.home() / ".aws" / "credentials"

    parser = configparser.RawConfigParser()
    for cfg_path in (aws_config, aws_credentials):
        if not cfg_path.exists():
            continue
        try:
            parser.read(cfg_path, encoding="utf-8")
            for section in parser.sections():
                if section.startswith("profile "):
                    profiles.add(section.replace("profile ", "", 1).strip())
                else:
                    profiles.add(section.strip())
        except Exception as e:
            logger.warning(f"Failed reading AWS profile config '{cfg_path}': {e}")

    if not profiles:
        profiles.add(_current_profile())
    return sorted(p for p in profiles if p)


maker_checker_roles = _load_maker_checker_roles()


def _list_iam_users_for_profile(profile: str, limit: int = 200) -> List[str]:
    if not profile:
        return []
    previous = os.environ.get("AWS_PROFILE", "")
    users: List[str] = []
    try:
        _activate_profile(profile)
        if MCP_AVAILABLE and aws_mcp:
            aws_mcp.rbac.initialize()
            client = aws_mcp.rbac.iam_client
        else:
            client = boto3.client("iam")

        marker = None
        while True:
            kwargs: Dict[str, Any] = {"MaxItems": min(100, max(1, limit))}
            if marker:
                kwargs["Marker"] = marker
            resp = client.list_users(**kwargs)
            for u in resp.get("Users", []):
                name = str(u.get("UserName", "")).strip()
                if name:
                    users.append(name)
                    if len(users) >= limit:
                        return sorted(set(users))
            if not resp.get("IsTruncated"):
                break
            marker = resp.get("Marker")
            if not marker:
                break
    except Exception as e:
        logger.info(f"Unable to list IAM users for profile '{profile}': {e}")
    finally:
        if previous:
            _activate_profile(previous)
    return sorted(set(users))


def _update_login_job(login_id: str, **fields: Any) -> None:
    with aws_login_lock:
        job = aws_login_jobs.get(login_id)
        if not job:
            return
        job.update(fields)
        job["updated_at"] = _utc_iso_now()


def _run_aws_login_job(login_id: str, profile: str, mode: str) -> None:
    """Background login runner with command fallbacks."""
    _run_aws_login_job_with_browser(login_id, profile, mode, browser_hint=None, client_key=None)


def _detect_browser_hint(user_agent: str) -> Optional[str]:
    ua = (user_agent or "").lower()
    if "safari" in ua and "chrome" not in ua and "chromium" not in ua:
        return "safari"
    if "chrome" in ua or "chromium" in ua:
        return "chrome"
    return None


def _browser_env_command(browser_hint: Optional[str]) -> Optional[str]:
    if not browser_hint:
        return None
    if sys.platform != "darwin":
        return None
    hint = browser_hint.lower().strip()
    if hint == "safari":
        return "/usr/bin/open -a Safari %s"
    if hint == "chrome":
        return "/usr/bin/open -a 'Google Chrome' %s"
    return None


def _run_aws_login_job_with_browser(
    login_id: str,
    profile: str,
    mode: str,
    browser_hint: Optional[str],
    client_key: Optional[str],
) -> None:
    """Background login runner with command fallbacks and browser hinting."""
    commands: List[List[str]] = []
    requested_mode = (mode or "auto").lower()
    if requested_mode in {"auto", "login"}:
        commands.append(["aws", "login", "--profile", profile])
    if requested_mode in {"auto", "sso"}:
        commands.append(["aws", "sso", "login", "--profile", profile])

    last_error = ""
    browser_cmd = _browser_env_command(browser_hint)
    cmd_env = os.environ.copy()
    cmd_env["AWS_PROFILE"] = profile
    cmd_env["AWS_DEFAULT_PROFILE"] = profile
    cmd_env["AWS_SDK_LOAD_CONFIG"] = "1"
    for env_key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        cmd_env.pop(env_key, None)
        os.environ.pop(env_key, None)
    if browser_cmd:
        cmd_env["BROWSER"] = browser_cmd

    for cmd in commands:
        _update_login_job(login_id, status="running", command=" ".join(cmd), message=f"Running {' '.join(cmd)} ...")
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=cmd_env)
            if proc.returncode == 0:
                sts_cmd = ["aws", "sts", "get-caller-identity", "--profile", profile, "--output", "json"]
                sts_proc = subprocess.run(sts_cmd, capture_output=True, text=True, timeout=30, env=cmd_env)
                account = ""
                arn = ""
                if sts_proc.returncode == 0 and (sts_proc.stdout or "").strip():
                    try:
                        ident = json.loads(sts_proc.stdout)
                        account = str(ident.get("Account", ""))
                        arn = str(ident.get("Arn", ""))
                    except Exception:
                        pass
                else:
                    last_error = (sts_proc.stderr or sts_proc.stdout or "Could not verify caller identity after login.").strip()
                    continue

                _activate_profile(profile)
                if client_key:
                    _set_client_profile(profile, client_key=client_key)
                if MCP_AVAILABLE and aws_mcp:
                    aws_mcp.rbac.initialize()
                _update_login_job(
                    login_id,
                    status="success",
                    message=f"Login completed for profile '{profile}'.",
                    stdout=(proc.stdout or "")[:2000],
                    stderr=(proc.stderr or "")[:2000],
                    account=account,
                    arn=arn,
                )
                return
            last_error = (proc.stderr or proc.stdout or f"exit_code={proc.returncode}").strip()
        except FileNotFoundError:
            last_error = "AWS CLI is not installed or not on PATH."
        except subprocess.TimeoutExpired:
            last_error = "Login command timed out after 5 minutes."
        except Exception as e:
            last_error = str(e)

    _update_login_job(
        login_id,
        status="failed",
        message=f"Failed to login profile '{profile}'.",
        error=last_error or "Unknown login error.",
    )


def _maker_checker_should_gate(tool_name: str, mcp_server: Optional[str], active_profile: Optional[str] = None) -> bool:
    if mcp_server != "aws_terraform":
        return False
    if not is_mutating_tool(tool_name):
        return False
    effective_profile = active_profile or _current_profile()
    if not _checker_profiles():
        return False
    return not _is_checker_profile(effective_profile)


def _create_maker_checker_request(
    run_id: str,
    thread_id: str,
    tool_name: str,
    tool_args: Dict[str, Any],
    mcp_server: str,
    requester_message: str = "",
    requester_profile: Optional[str] = None,
) -> Dict[str, Any]:
    request_id = f"mc-{uuid.uuid4().hex[:12]}"
    effective_requester = requester_profile or _current_profile()
    comments: List[Dict[str, Any]] = []
    if requester_message:
        comments.append({
            "timestamp": _utc_iso_now(),
            "author_profile": effective_requester,
            "author_role": "maker",
            "message": requester_message,
        })
    item = {
        "request_id": request_id,
        "created_at": _utc_iso_now(),
        "updated_at": _utc_iso_now(),
        "run_id": run_id,
        "thread_id": thread_id,
        "requester_profile": effective_requester,
        "checker_profiles": _checker_profiles(),
        "checker_profile": _primary_checker_profile(),
        "tool_name": tool_name,
        "tool_args": tool_args or {},
        "mcp_server": mcp_server,
        "status": "pending",
        "approval_notes": "",
        "approved_at": None,
        "rejected_at": None,
        "executed_at": None,
        "plan_preview": "",
        "execution_result": None,
        "execution_error": None,
        "comments": comments,
    }
    item["plan_preview"] = _build_maker_checker_plan_preview(item)
    with maker_checker_lock:
        maker_checker_requests[request_id] = item
    return item


def _list_maker_checker_requests(status: Optional[str] = None) -> List[Dict[str, Any]]:
    with maker_checker_lock:
        values = list(maker_checker_requests.values())
    if status:
        values = [v for v in values if str(v.get("status", "")).lower() == status.lower()]
    values.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return values


def _maker_checker_copy(item: Dict[str, Any]) -> Dict[str, Any]:
    return json.loads(json.dumps(item, default=str))


def _build_maker_checker_plan_preview(item: Dict[str, Any]) -> str:
    tool_name = item.get("tool_name", "")
    tool_args = item.get("tool_args", {}) or {}

    if tool_name in {"terraform_apply", "terraform_destroy"}:
        project_name = tool_args.get("project_name")
        if project_name and aws_mcp:
            tfplan = aws_mcp.terraform.workspace_dir / project_name / "tfplan"
            if tfplan.exists():
                cmd = ["terraform", "-chdir", str(aws_mcp.terraform.workspace_dir / project_name), "show", "tfplan"]
                try:
                    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
                    if proc.returncode == 0 and proc.stdout.strip():
                        return proc.stdout[:12000]
                    if proc.stderr.strip():
                        return f"Unable to render tfplan preview: {proc.stderr[:1000]}"
                except Exception as e:
                    return f"Unable to render tfplan preview: {str(e)}"
            return f"No tfplan file found for project '{project_name}'."
        return "No project_name supplied to render terraform plan preview."

    if tool_name.startswith("create_"):
        return (
            "Planned tool request (pre-Terraform plan):\n"
            f"tool: {tool_name}\n"
            f"arguments: {json.dumps(tool_args, indent=2, default=str)}\n"
            "Note: terraform plan will be available after project creation in execution stage."
        )

    return (
        "Planned request preview:\n"
        f"tool: {tool_name}\n"
        f"arguments: {json.dumps(tool_args, indent=2, default=str)}"
    )


def _audit_is_mutating_tool(tool_name: str) -> bool:
    """Audit-local mutating classification for tool names."""
    if is_mutating_tool(tool_name):
        return True
    return tool_name in {
        "create_ecs_service",
        "start_ecs_deployment_workflow",
        "update_ecs_deployment_workflow",
        "review_ecs_deployment_workflow",
        "deploy_architecture",
    }


def _iter_audit_events(channel: str = "agui") -> Iterable[Dict[str, Any]]:
    """Yield workflow events from rotated JSONL files in chronological file order."""
    base = os.path.join(WORKFLOW_LOG_DIR, f"workflow_execution_log_{channel}.jsonl")
    paths = sorted(glob.glob(f"{base}*"))
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(record, dict):
                        yield record
        except FileNotFoundError:
            continue


def _audit_cloud_for_tool(tool_name: str) -> str:
    lower = (tool_name or "").lower()
    if "azure" in lower:
        return "azure"
    return "aws"


def _audit_extract_resource(tool_name: str, tool_args: Dict[str, Any], tool_result: Dict[str, Any]) -> str:
    """Best-effort resource label from tool args/result."""
    if tool_args:
        for key in ("bucket_name", "db_name", "function_name", "project_name", "workflow_id", "resource_id", "cluster_name", "service_name"):
            value = tool_args.get(key)
            if value:
                return str(value)
    if tool_result:
        for key in ("project_name", "resource_id", "workflow_id"):
            value = tool_result.get(key)
            if value:
                return str(value)
    return "n/a"


def _audit_extract_details(tool_result: Dict[str, Any]) -> str:
    if not isinstance(tool_result, dict):
        return str(tool_result)[:600]
    if tool_result.get("error"):
        return str(tool_result.get("error"))[:600]
    if tool_result.get("message"):
        return str(tool_result.get("message"))[:600]
    for key in ("stdout", "details"):
        value = tool_result.get(key)
        if value:
            return str(value).replace("\n", " ")[:600]
    return "tool executed"


def _collect_audit_entries(
    cloud: Optional[str] = None,
    status: Optional[str] = None,
    action: Optional[str] = None,
    user: Optional[str] = None,
    limit: int = 500,
) -> Tuple[List[Dict[str, Any]], Dict[str, int], Dict[str, List[str]]]:
    started_by_call: Dict[Tuple[str, str], Dict[str, Any]] = {}
    actor_by_run: Dict[str, str] = {}
    entries: List[Dict[str, Any]] = []

    for record in _iter_audit_events(channel="agui"):
        event_type = record.get("event_type")
        run_id = record.get("run_id", "")
        tool_name = record.get("tool_name", "")
        tool_call_id = record.get("tool_call_id", "")
        key = (run_id, tool_call_id)

        if event_type == "tool_execution_started":
            started_by_call[key] = record.get("tool_args", {}) or {}
            continue

        if event_type == "tool_execution_completed":
            result = record.get("tool_result", {}) or {}
            if tool_name == "get_user_permissions" and result.get("success"):
                actor = (result.get("user_info", {}) or {}).get("user_arn") or (result.get("user_info", {}) or {}).get("account_id")
                if actor:
                    actor_by_run[run_id] = str(actor)

            if not _audit_is_mutating_tool(tool_name):
                continue

            entry_status = "success" if record.get("success", False) else "failed"
            tool_args = started_by_call.get(key, {})
            cloud_name = _audit_cloud_for_tool(tool_name)
            actor = actor_by_run.get(run_id, "unknown")
            entry = {
                "timestamp": record.get("timestamp"),
                "run_id": run_id,
                "thread_id": record.get("thread_id"),
                "user": actor,
                "cloud": cloud_name,
                "action": tool_name,
                "resource": _audit_extract_resource(tool_name, tool_args, result),
                "status": entry_status,
                "details": _audit_extract_details(result),
                "tool_args": tool_args,
            }
            entries.append(entry)
            continue

        if event_type in {"tool_execution_failed", "tool_execution_blocked"} and _audit_is_mutating_tool(tool_name):
            tool_args = started_by_call.get(key, {})
            cloud_name = _audit_cloud_for_tool(tool_name)
            actor = actor_by_run.get(run_id, "unknown")
            failed_status = "blocked" if event_type == "tool_execution_blocked" else "failed"
            details = record.get("reason") or record.get("error") or event_type
            entries.append({
                "timestamp": record.get("timestamp"),
                "run_id": run_id,
                "thread_id": record.get("thread_id"),
                "user": actor,
                "cloud": cloud_name,
                "action": tool_name,
                "resource": _audit_extract_resource(tool_name, tool_args, {}),
                "status": failed_status,
                "details": str(details)[:600],
                "tool_args": tool_args,
            })

    # Include maker-checker approval/execution timeline in audit list.
    for item in _list_maker_checker_requests():
        comments = item.get("comments", []) or []
        comment_lines = [
            f"{c.get('author_role', 'user')}({c.get('author_profile', 'unknown')}): {c.get('message', '')}"
            for c in comments[-4:]
        ]
        details = " | ".join(comment_lines) if comment_lines else ""
        if item.get("execution_error"):
            details = f"{details} | exec_error: {item.get('execution_error')}".strip(" |")
        elif item.get("execution_result"):
            result = item.get("execution_result") or {}
            result_excerpt = ""
            if isinstance(result, dict):
                result_excerpt = (
                    str(result.get("stdout") or result.get("message") or result.get("error") or "")
                    .replace("\n", " ")
                    .strip()
                )
            details = f"{details} | execution completed | {result_excerpt}".strip(" |")
        elif item.get("approval_notes"):
            details = f"{details} | approval: {item.get('approval_notes')}".strip(" |")

        entries.append({
            "timestamp": item.get("updated_at") or item.get("created_at"),
            "run_id": item.get("run_id"),
            "thread_id": item.get("thread_id"),
            "user": item.get("requester_profile", "unknown"),
            "cloud": "aws",
            "action": f"maker_checker:{item.get('tool_name', 'unknown')}",
            "resource": _audit_extract_resource(item.get("tool_name", ""), item.get("tool_args", {}), item.get("execution_result") or {}),
            "status": item.get("status", "pending"),
            "details": details[:1400] or "maker-checker workflow",
            "tool_args": item.get("tool_args", {}),
        })

    entries.sort(key=lambda x: x.get("timestamp") or "", reverse=True)

    def _match(v: Optional[str], expected: Optional[str]) -> bool:
        if not expected:
            return True
        return str(v or "").lower() == expected.lower()

    filtered = [
        entry for entry in entries
        if _match(entry.get("cloud"), cloud)
        and _match(entry.get("status"), status)
        and _match(entry.get("action"), action)
        and _match(entry.get("user"), user)
    ]

    if limit > 0:
        filtered = filtered[:limit]

    summary = {
        "total": len(filtered),
        "successful": sum(1 for e in filtered if e.get("status") == "success"),
        "failed": sum(1 for e in filtered if e.get("status") == "failed"),
        "blocked": sum(1 for e in filtered if e.get("status") == "blocked"),
    }

    filters = {
        "clouds": sorted({e.get("cloud") for e in entries if e.get("cloud")}),
        "statuses": sorted({e.get("status") for e in entries if e.get("status")}),
        "actions": sorted({e.get("action") for e in entries if e.get("action")}),
        "users": sorted({e.get("user") for e in entries if e.get("user")}),
    }

    return filtered, summary, filters


def get_mcp_server(server_name: Optional[str]):
    if server_name == "aws_terraform":
        return aws_mcp if AWS_MCP_AVAILABLE else None
    if server_name == "azure_terraform":
        return azure_mcp if AZURE_MCP_AVAILABLE else None
    return None


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


@app.get("/audit")
async def audit_page():
    logger.debug("Serving audit.html")
    return FileResponse(f"{UI_DIR}/audit.html")


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


@app.get("/api/audit/logs")
async def list_audit_logs(
    cloud: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    action: Optional[str] = Query(default=None),
    user: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
):
    logger.info("API Request: GET /api/audit/logs")
    entries, summary, filters = _collect_audit_entries(
        cloud=cloud,
        status=status,
        action=action,
        user=user,
        limit=limit,
    )
    return JSONResponse({
        "summary": summary,
        "entries": entries,
        "filters": filters,
        "applied": {
            "cloud": cloud,
            "status": status,
            "action": action,
            "user": user,
            "limit": limit,
        },
    })


@app.get("/api/audit/export")
async def export_audit_logs(
    cloud: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    action: Optional[str] = Query(default=None),
    user: Optional[str] = Query(default=None),
):
    logger.info("API Request: GET /api/audit/export")
    entries, _summary, _filters = _collect_audit_entries(
        cloud=cloud,
        status=status,
        action=action,
        user=user,
        limit=2000,
    )

    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=["timestamp", "user", "cloud", "action", "resource", "status", "details", "run_id", "thread_id"],
    )
    writer.writeheader()
    for entry in entries:
        writer.writerow({
            "timestamp": entry.get("timestamp", ""),
            "user": entry.get("user", ""),
            "cloud": entry.get("cloud", ""),
            "action": entry.get("action", ""),
            "resource": entry.get("resource", ""),
            "status": entry.get("status", ""),
            "details": entry.get("details", ""),
            "run_id": entry.get("run_id", ""),
            "thread_id": entry.get("thread_id", ""),
        })

    filename = f"audit-log-{time.strftime('%Y%m%d-%H%M%S')}.csv"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv", headers=headers)


@app.get("/api/mcp/status")
async def mcp_status(mcpServer: str = Query(default="aws_terraform")):
    """Get MCP server status"""
    logger.info(f"API Request: GET /api/mcp/status - Server: {mcpServer}")
    mcp_server = get_mcp_server(mcpServer)

    if not MCP_AVAILABLE or mcp_server is None:
        return JSONResponse({
            "available": False,
            "message": f"MCP Server not available: {mcpServer}"
        })
    
    try:
        init_result = mcp_server.initialize()
        return JSONResponse({
            "available": True,
            "server": mcpServer,
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
async def list_mcp_tools(mcpServer: str = Query(default="aws_terraform")):
    """List available MCP tools"""
    logger.info(f"API Request: GET /api/mcp/tools - Server: {mcpServer}")
    mcp_server = get_mcp_server(mcpServer)

    if not MCP_AVAILABLE or mcp_server is None:
        return JSONResponse({"tools": [], "error": "MCP Server not available"})
    
    try:
        tools = mcp_server.list_tools()
        logger.info(f"Returning {len(tools)} MCP tools")
        return JSONResponse({"tools": tools, "server": mcpServer})
    except Exception as e:
        logger.error(f"Failed to list MCP tools: {e}")
        return JSONResponse({"tools": [], "error": str(e)})


class MCPToolRequest(BaseModel):
    tool_name: str
    parameters: Dict[str, Any]
    mcpServer: Optional[str] = "aws_terraform"


class MakerCheckerDecisionRequest(BaseModel):
    request_id: str
    notes: Optional[str] = None


class MakerCheckerCommentRequest(BaseModel):
    request_id: str
    message: str


class MakerCheckerRolesUpdateRequest(BaseModel):
    checker_profiles: Optional[List[str]] = None
    maker_profiles: Optional[List[str]] = None


@app.post("/api/mcp/execute")
async def execute_mcp_tool(request: MCPToolRequest, http_request: Request):
    """Execute an MCP tool"""
    logger.info(f"API Request: POST /api/mcp/execute - Server: {request.mcpServer}, Tool: {request.tool_name}")
    logger.info(f"Parameters: {request.parameters}")

    mcp_server = get_mcp_server(request.mcpServer)
    if not MCP_AVAILABLE or mcp_server is None:
        return JSONResponse({
            "success": False,
            "error": "MCP Server not available"
        })
    
    try:
        _activate_profile(_current_profile(http_request))
        result = mcp_server.execute_tool(request.tool_name, request.parameters)
        logger.info(f"MCP tool execution result: {result.get('success', False)}")
        return JSONResponse(result)
    except Exception as e:
        logger.error(f"MCP tool execution failed: {e}", exc_info=True)
        return JSONResponse({
            "success": False,
            "error": str(e)
        })


@app.get("/api/maker-checker/config")
async def maker_checker_config(request: Request):
    pending = len(_list_maker_checker_requests(status="pending"))
    current = _current_profile(request)
    checkers = _checker_profiles()
    makers = _maker_profiles()
    return JSONResponse({
        "checker_profile": checkers[0] if checkers else "",
        "checker_profiles": checkers,
        "maker_profiles": makers,
        "current_profile": current,
        "is_checker": _is_checker_profile(current),
        "is_maker": _is_maker_profile(current),
        "pending_count": pending,
    })


@app.get("/api/maker-checker/roles")
async def maker_checker_roles_config(request: Request):
    profiles = _list_aws_profiles()
    current = _current_profile(request)
    checkers = _checker_profiles()
    makers = _maker_profiles()
    iam_users = _list_iam_users_for_profile(current, limit=200) if current else []
    return JSONResponse({
        "profiles": profiles,
        "iam_users": iam_users,
        "checker_profiles": checkers,
        "maker_profiles": makers,
        "current_profile": current,
        "is_checker": _is_checker_profile(current),
        "is_maker": _is_maker_profile(current),
    })


@app.post("/api/maker-checker/roles")
async def update_maker_checker_roles(payload: MakerCheckerRolesUpdateRequest):
    available_profiles = _list_aws_profiles()
    incoming_checkers = _normalize_profiles(payload.checker_profiles or [])
    incoming_makers = _normalize_profiles(payload.maker_profiles or [])
    if not incoming_checkers:
        return JSONResponse({"success": False, "error": "At least one checker profile is required."})

    unknown = [p for p in incoming_checkers + incoming_makers if p not in available_profiles]
    if unknown:
        return JSONResponse({
            "success": False,
            "error": f"Unknown profile(s): {', '.join(unknown)}",
        })

    if not incoming_makers:
        incoming_makers = [p for p in available_profiles if p not in incoming_checkers]
    else:
        incoming_makers = [p for p in incoming_makers if p not in incoming_checkers]

    new_config = {
        "checker_profiles": incoming_checkers,
        "maker_profiles": incoming_makers,
    }
    with maker_checker_roles_lock:
        maker_checker_roles["checker_profiles"] = list(incoming_checkers)
        maker_checker_roles["maker_profiles"] = list(incoming_makers)
    _save_maker_checker_roles(new_config)

    return JSONResponse({
        "success": True,
        "checker_profiles": incoming_checkers,
        "maker_profiles": incoming_makers,
    })


@app.get("/api/maker-checker/requests")
async def maker_checker_requests_api(status: Optional[str] = Query(default=None)):
    return JSONResponse({"requests": _list_maker_checker_requests(status=status)})


@app.get("/api/maker-checker/request/{request_id}")
async def maker_checker_request_detail(request_id: str):
    with maker_checker_lock:
        item = maker_checker_requests.get(request_id)
        if not item:
            return JSONResponse({"success": False, "error": f"Request '{request_id}' not found."})
        return JSONResponse({"success": True, "request": _maker_checker_copy(item)})


@app.post("/api/maker-checker/comment")
async def maker_checker_add_comment(request: Request, payload: MakerCheckerCommentRequest):
    message = (payload.message or "").strip()
    if not message:
        return JSONResponse({"success": False, "error": "message is required"})

    with maker_checker_lock:
        item = maker_checker_requests.get(payload.request_id)
        if not item:
            return JSONResponse({"success": False, "error": f"Request '{payload.request_id}' not found."})
        role = "checker" if _is_checker_profile(_current_profile(request)) else "maker"
        item.setdefault("comments", []).append({
            "timestamp": _utc_iso_now(),
            "author_profile": _current_profile(request),
            "author_role": role,
            "message": message,
        })
        item["updated_at"] = _utc_iso_now()
        updated = _maker_checker_copy(item)

    workflow_event(
        workflow_logger,
        "maker_checker_comment_added",
        source="agui",
        run_id=item.get("run_id"),
        thread_id=item.get("thread_id"),
        request_id=item.get("request_id"),
        metadata={"class": "MakerChecker", "method": "comment"},
    )
    return JSONResponse({"success": True, "request": updated})


@app.post("/api/maker-checker/approve")
async def approve_maker_checker_request(request: Request, payload: MakerCheckerDecisionRequest):
    current = _current_profile(request)
    if not _is_checker_profile(current):
        return JSONResponse({
            "success": False,
            "error": f"Approval requires checker profile ({', '.join(_checker_profiles())}). Current profile is '{current}'.",
        })

    with maker_checker_lock:
        item = maker_checker_requests.get(payload.request_id)
        if not item:
            return JSONResponse({"success": False, "error": f"Request '{payload.request_id}' not found."})
        if item.get("status") != "pending":
            return JSONResponse({"success": False, "error": f"Request '{payload.request_id}' is not pending."})
        item["status"] = "approved"
        item["approval_notes"] = payload.notes or ""
        item["approved_at"] = _utc_iso_now()
        item["updated_at"] = _utc_iso_now()
        if payload.notes:
            item.setdefault("comments", []).append({
                "timestamp": _utc_iso_now(),
                "author_profile": _current_profile(request),
                "author_role": "checker",
                "message": payload.notes,
            })
        updated = _maker_checker_copy(item)

    workflow_event(
        workflow_logger,
        "maker_checker_request_approved",
        source="agui",
        run_id=item.get("run_id"),
        thread_id=item.get("thread_id"),
        request_id=item.get("request_id"),
        tool_name=item.get("tool_name"),
        metadata={"class": "MakerChecker", "method": "approve"},
    )
    return JSONResponse({"success": True, "request": updated})


@app.post("/api/maker-checker/reject")
async def reject_maker_checker_request(request: Request, payload: MakerCheckerDecisionRequest):
    current = _current_profile(request)
    if not _is_checker_profile(current):
        return JSONResponse({
            "success": False,
            "error": f"Rejection requires checker profile ({', '.join(_checker_profiles())}). Current profile is '{current}'.",
        })

    with maker_checker_lock:
        item = maker_checker_requests.get(payload.request_id)
        if not item:
            return JSONResponse({"success": False, "error": f"Request '{payload.request_id}' not found."})
        if item.get("status") != "pending":
            return JSONResponse({"success": False, "error": f"Request '{payload.request_id}' is not pending."})
        item["status"] = "rejected"
        item["approval_notes"] = payload.notes or ""
        item["rejected_at"] = _utc_iso_now()
        item["updated_at"] = _utc_iso_now()
        if payload.notes:
            item.setdefault("comments", []).append({
                "timestamp": _utc_iso_now(),
                "author_profile": _current_profile(request),
                "author_role": "checker",
                "message": payload.notes,
            })
        updated = _maker_checker_copy(item)

    workflow_event(
        workflow_logger,
        "maker_checker_request_rejected",
        source="agui",
        run_id=item.get("run_id"),
        thread_id=item.get("thread_id"),
        request_id=item.get("request_id"),
        tool_name=item.get("tool_name"),
        metadata={"class": "MakerChecker", "method": "reject"},
    )
    return JSONResponse({"success": True, "request": updated})


@app.post("/api/maker-checker/execute")
async def execute_maker_checker_request(request: Request, payload: MakerCheckerDecisionRequest):
    with maker_checker_lock:
        item = maker_checker_requests.get(payload.request_id)
        if not item:
            return JSONResponse({"success": False, "error": f"Request '{payload.request_id}' not found."})
        if item.get("status") != "approved":
            return JSONResponse({"success": False, "error": f"Request '{payload.request_id}' is not approved yet."})
        item["status"] = "executing"
        item["updated_at"] = _utc_iso_now()
        if payload.notes:
            role = "checker" if _is_checker_profile(_current_profile(request)) else "maker"
            item.setdefault("comments", []).append({
                "timestamp": _utc_iso_now(),
                "author_profile": _current_profile(request),
                "author_role": role,
                "message": payload.notes,
            })

    selected_mcp = get_mcp_server(item.get("mcp_server"))
    if not selected_mcp:
        with maker_checker_lock:
            item["status"] = "failed"
            item["execution_error"] = f"MCP server '{item.get('mcp_server')}' not available."
            item["updated_at"] = _utc_iso_now()
            failed = _maker_checker_copy(item)
        return JSONResponse({"success": False, "error": failed["execution_error"], "request": failed})

    previous_profile = _current_profile(request)
    checker_target = _primary_checker_profile()
    if checker_target:
        _activate_profile(checker_target)
    try:
        if MCP_AVAILABLE and aws_mcp:
            aws_mcp.rbac.initialize()
        result = selected_mcp.execute_tool(item["tool_name"], item.get("tool_args", {}))
    except Exception as e:
        result = {"success": False, "error": str(e)}
    finally:
        _activate_profile(previous_profile)
        if MCP_AVAILABLE and aws_mcp:
            aws_mcp.rbac.initialize()

    with maker_checker_lock:
        item["execution_result"] = result
        item["executed_at"] = _utc_iso_now()
        item["updated_at"] = _utc_iso_now()
        item["status"] = "executed" if result.get("success", False) else "failed"
        if not result.get("success", False):
            item["execution_error"] = result.get("error") or "Execution failed."
        updated = _maker_checker_copy(item)

    workflow_event(
        workflow_logger,
        "maker_checker_request_executed",
        source="agui",
        run_id=item.get("run_id"),
        thread_id=item.get("thread_id"),
        request_id=item.get("request_id"),
        tool_name=item.get("tool_name"),
        status=item.get("status"),
        metadata={"class": "MakerChecker", "method": "execute"},
    )
    return JSONResponse({"success": True, "request": updated})


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
async def get_aws_identity(request: Request):
    """Get current AWS identity and check if session is active"""
    logger.info("API Request: GET /api/aws/identity")
    if not MCP_AVAILABLE or aws_mcp is None:
        return JSONResponse({"active": False, "error": "MCP not available"})
    
    try:
        active_profile = _current_profile(request)
        _activate_profile(active_profile)
        # Re-initialize to catch new credentials
        aws_mcp.rbac.initialize()
        info = aws_mcp.rbac.get_user_info()
        
        if "error" in info:
             return JSONResponse({
                "active": False,
                "error": info["error"],
                "profile": active_profile
            })

        regions = aws_mcp.rbac.get_allowed_regions()
        arn = info.get("user_arn")
        return JSONResponse({
            "active": True,
            "account": info.get("account_id"),
            "arn": arn,
            "user_name": _extract_user_name_from_arn(arn),
            "regions": regions,
            "profile": active_profile
        })
    except Exception as e:
        logger.warning(f"Failed to get AWS identity: {e}")
        return JSONResponse({
            "active": False,
            "error": str(e)
        })


@app.post("/api/aws/profile")
async def set_aws_profile(request: Request, payload: Dict[str, str]):
    """Set the active AWS profile for the server process"""
    profile = payload.get("profile", _current_profile(request))
    logger.info(f"API Request: POST /api/aws/profile - New Profile: {profile}")
    _set_client_profile(profile, request=request)
    _activate_profile(profile)
    
    # Force re-initialization of MCP
    if MCP_AVAILABLE and aws_mcp:
        aws_mcp.rbac.initialize()
        
    return JSONResponse({"success": True, "profile": profile, "client_key": _client_key_from_request(request)})


@app.get("/api/aws/profiles")
async def list_aws_profiles(request: Request):
    """List available AWS CLI profiles discovered from ~/.aws config."""
    profiles = _list_aws_profiles()
    return JSONResponse({
        "profiles": profiles,
        "current_profile": _current_profile(request),
        "checker_profile": _primary_checker_profile(),
        "checker_profiles": _checker_profiles(),
        "maker_profiles": _maker_profiles(),
    })


@app.post("/api/aws/login")
async def trigger_aws_login(request: Request, payload: Dict[str, str] = None):
    """Start AWS login flow and track status for UI polling callback."""
    global aws_login_latest_id
    profile = (payload or {}).get("profile") or _current_profile(request)
    mode = (payload or {}).get("mode", "auto")
    browser_hint = (payload or {}).get("browser") or _detect_browser_hint(request.headers.get("user-agent", ""))
    client_key = _client_key_from_request(request)
    logger.info(f"API Request: POST /api/aws/login - Profile: {profile}, Mode: {mode}, Browser Hint: {browser_hint or 'default'}")

    if not shutil.which("aws"):
        return JSONResponse({"success": False, "error": "AWS CLI not found. Install AWS CLI v2 and retry."})

    login_id = f"login-{uuid.uuid4().hex[:10]}"
    job = {
        "login_id": login_id,
        "profile": profile,
        "mode": mode,
        "status": "queued",
        "message": f"Starting login for profile '{profile}'...",
        "command": "",
        "error": "",
        "stdout": "",
        "stderr": "",
        "created_at": _utc_iso_now(),
        "updated_at": _utc_iso_now(),
        "browser_hint": browser_hint or "",
        "account": "",
        "arn": "",
        "client_key": client_key,
    }
    with aws_login_lock:
        aws_login_jobs[login_id] = job
        aws_login_latest_id = login_id

    t = threading.Thread(
        target=_run_aws_login_job_with_browser,
        args=(login_id, profile, mode, browser_hint, client_key),
        daemon=True,
    )
    t.start()
    return JSONResponse({
        "success": True,
        "login_id": login_id,
        "status": "queued",
        "message": "Login started. Browser should open for AWS authentication.",
    })


@app.get("/api/aws/login/status")
async def aws_login_status(login_id: Optional[str] = Query(default=None)):
    lookup_id = login_id
    with aws_login_lock:
        if not lookup_id:
            lookup_id = aws_login_latest_id
        job = aws_login_jobs.get(lookup_id) if lookup_id else None
    if not job:
        return JSONResponse({"success": False, "error": "No login job found."})
    return JSONResponse({"success": True, "job": job})


def get_llm(provider: str, model: Optional[str], credential_source: Optional[str], mcp_server_name: Optional[str] = "none"):
    cache_key = f"{provider}:{model or ''}:{credential_source or 'auto'}:{mcp_server_name or 'none'}"
    if cache_key in llm_cache:
        logger.debug(f"LLM cache hit: {cache_key}")
        return llm_cache[cache_key]

    logger.info(f"Initializing LLM - Provider: {provider}, Model: {model or 'default'}, Credential Source: {credential_source or 'auto'}, MCP: {mcp_server_name}")
    llm = initialize_llm(provider, model=model, preferred_source=credential_source)
    
    # Bind tools if MCP server is selected
    selected_mcp = get_mcp_server(mcp_server_name)
    if mcp_server_name != "none" and MCP_AVAILABLE and selected_mcp:
        tools = selected_mcp.list_tools()
        try:
            llm = llm.bind_tools(tools)
            logger.info(f"Successfully bound {len(tools)} tools from MCP server: {mcp_server_name}")
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
async def run_agent(payload: RunRequest, request: Request):
    logger.info("=" * 80)
    logger.info("API Request: POST /api/run - New user query received")
    logger.info(f"Provider: {payload.provider}, Model: {payload.model or 'default'}")
    logger.info(f"Credential Source: {payload.credentialSource or 'auto'}")
    logger.info(f"Thread ID: {payload.threadId}")
    logger.info(f"MCP Server: {payload.mcpServer}")
    logger.info(f"Message Length: {len(payload.message)} characters")
    active_profile = _current_profile(request)
    _activate_profile(active_profile)
    
    if not payload.message.strip():
        logger.warning("Request rejected: Empty message")
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if payload.provider not in SUPPORTED_LLMS:
        logger.error(f"Request rejected: Unsupported provider '{payload.provider}'")
        raise HTTPException(status_code=400, detail="Unsupported provider")

    run_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    thread_id = payload.threadId or str(uuid.uuid4())
    workflow_event(
        workflow_logger,
        "query_received",
        source="agui",
        run_id=run_id,
        thread_id=thread_id,
        message_id=message_id,
        provider=payload.provider,
        model=payload.model or "default",
        mcp_server=payload.mcpServer,
        metadata={"class": "FastAPI", "method": "run_agent"},
        user_query=payload.message,
    )
    
    logger.info(f"Run ID: {run_id}")
    logger.info(f"Message ID: {message_id}")

    if is_audience_request(payload.message):
        response_text = build_audience_response()
        workflow_event(
            workflow_logger,
            "audience_request",
            source="agui",
            run_id=run_id,
            thread_id=thread_id,
            metadata={"class": "FastAPI", "method": "run_agent"},
        )

        def stream_capabilities():
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
            chunk_size = 100
            for idx in range(0, len(response_text), chunk_size):
                chunk = response_text[idx: idx + chunk_size]
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
            yield sse_event({
                "type": "RUN_FINISHED",
                "runId": run_id,
                "threadId": thread_id,
                "timestamp": now_ms(),
            })
            workflow_event(
                workflow_logger,
                "run_finished",
                source="agui",
                run_id=run_id,
                thread_id=thread_id,
                metadata={"class": "FastAPI", "method": "run_agent"},
            )

        return StreamingResponse(
            stream_capabilities(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    if is_capabilities_request(payload.message):
        active_mcp = get_mcp_server(payload.mcpServer)
        response_text = build_capabilities_response(payload.mcpServer, active_mcp, payload.message)
        workflow_event(
            workflow_logger,
            "capabilities_request",
            source="agui",
            run_id=run_id,
            thread_id=thread_id,
            metadata={"class": "FastAPI", "method": "run_agent"},
        )

        def stream_capabilities():
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
            chunk_size = 100
            for idx in range(0, len(response_text), chunk_size):
                chunk = response_text[idx: idx + chunk_size]
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
            yield sse_event({
                "type": "RUN_FINISHED",
                "runId": run_id,
                "threadId": thread_id,
                "timestamp": now_ms(),
            })
            workflow_event(
                workflow_logger,
                "run_finished",
                source="agui",
                run_id=run_id,
                thread_id=thread_id,
                metadata={"class": "FastAPI", "method": "run_agent"},
            )

        return StreamingResponse(
            stream_capabilities(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    history = conversation_store.setdefault(thread_id, [])
    if not history:
        history.append(SystemMessage(content=EXECUTION_SYSTEM_PROMPT))
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
            workflow_event(
                workflow_logger,
                "run_started",
                source="agui",
                run_id=run_id,
                thread_id=thread_id,
                metadata={"class": "FastAPI", "method": "run_agent.stream"},
            )
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
            forced_followup_text = ""
            last_successful_plan_project: Optional[str] = None
            while iteration < max_iterations:
                workflow_event(
                    workflow_logger,
                    "llm_invocation_started",
                    source="agui",
                    run_id=run_id,
                    thread_id=thread_id,
                    iteration=iteration + 1,
                    metadata={"class": "LLM", "method": "invoke"},
                )
                try:
                    response = llm.invoke(history)
                except Exception as llm_err:
                    err_text = str(llm_err)
                    if (
                        payload.provider == "perplexity"
                        and payload.mcpServer != "none"
                        and "Tool calling is not supported for this model" in err_text
                    ):
                        logger.warning(
                            f"[{run_id}] Perplexity model rejected tool calling for MCP request. Falling back to guidance response."
                        )
                        forced_followup_text = (
                            "Perplexity (Sonar) does not support MCP tool calling for this request. "
                            "No MCP tools were executed. Switch to GPT-4o or Gemini and re-run the same prompt."
                        )
                        response = AIMessage(content="")
                        history.append(response)
                        break
                    raise
                history.append(response)
                
                # If there are tool calls, execute them
                tool_calls = extract_tool_calls(response)
                if tool_calls:
                    # Guardrail: dedupe exact repeated tool calls in one LLM step.
                    deduped_tool_calls = []
                    seen_tool_calls = set()
                    for tool_call in tool_calls:
                        tool_name = tool_call.get("name")
                        tool_args = tool_call.get("args", {}) or {}
                        try:
                            signature = (tool_name, json.dumps(tool_args, sort_keys=True, default=str))
                        except Exception:
                            signature = (tool_name, str(tool_args))
                        if signature in seen_tool_calls:
                            logger.warning(f"[{run_id}] Skipping duplicate tool call in same iteration: {tool_name} {tool_args}")
                            continue
                        seen_tool_calls.add(signature)
                        deduped_tool_calls.append(tool_call)
                    tool_calls = deduped_tool_calls

                    logger.info(f"[{run_id}] LLM requested {len(tool_calls)} tool calls")
                    workflow_event(
                        workflow_logger,
                        "tool_calls_requested",
                        source="agui",
                        run_id=run_id,
                        thread_id=thread_id,
                        iteration=iteration + 1,
                        tool_count=len(tool_calls),
                        metadata={"class": "LLM", "method": "invoke"},
                    )
                    
                    for tool_call in tool_calls:
                        tool_name = tool_call["name"]
                        tool_args = tool_call["args"]
                        tool_call_id = tool_call["id"]

                        if tool_name == "terraform_apply" and payload.mcpServer == "aws_terraform" and aws_mcp:
                            requested_project = (tool_args or {}).get("project_name")

                            def _has_tfplan(project: Optional[str]) -> bool:
                                if not project:
                                    return False
                                return (aws_mcp.terraform.workspace_dir / project / "tfplan").exists()

                            if requested_project and not _has_tfplan(requested_project):
                                if last_successful_plan_project and _has_tfplan(last_successful_plan_project):
                                    logger.warning(
                                        f"[{run_id}] terraform_apply requested project '{requested_project}' without tfplan. "
                                        f"Using last successfully planned project '{last_successful_plan_project}' instead."
                                    )
                                    tool_args = dict(tool_args)
                                    tool_args["project_name"] = last_successful_plan_project
                            elif not requested_project and last_successful_plan_project and _has_tfplan(last_successful_plan_project):
                                logger.warning(
                                    f"[{run_id}] terraform_apply missing project_name. "
                                    f"Using last successfully planned project '{last_successful_plan_project}'."
                                )
                                tool_args = dict(tool_args)
                                tool_args["project_name"] = last_successful_plan_project
                        
                        logger.info(f"[{run_id}] Executing tool: {tool_name} with args: {tool_args}")
                        workflow_event(
                            workflow_logger,
                            "tool_execution_started",
                            source="agui",
                            run_id=run_id,
                            thread_id=thread_id,
                            tool_name=tool_name,
                            tool_call_id=tool_call_id,
                            tool_args=tool_args,
                            metadata={"class": "MCPServer", "method": "execute_tool"},
                        )

                        if read_only_intent and is_mutating_tool(tool_name):
                            logger.warning(f"[{run_id}] Blocked mutating tool '{tool_name}' due to read-only user intent")
                            workflow_event(
                                workflow_logger,
                                "tool_execution_blocked",
                                source="agui",
                                run_id=run_id,
                                thread_id=thread_id,
                                tool_name=tool_name,
                                reason="read_only_intent",
                                metadata={"class": "IntentPolicy", "method": "is_mutating_tool"},
                            )
                            history.append(ToolMessage(
                                content=json.dumps({
                                    "success": False,
                                    "error": f"Blocked mutating tool '{tool_name}' because user intent is read-only. Use discovery/list tools instead."
                                }),
                                tool_call_id=tool_call_id
                            ))
                            continue

                        if _maker_checker_should_gate(tool_name, payload.mcpServer, active_profile=active_profile):
                            request_item = _create_maker_checker_request(
                                run_id=run_id,
                                thread_id=thread_id,
                                tool_name=tool_name,
                                tool_args=tool_args,
                                mcp_server=payload.mcpServer or "aws_terraform",
                                requester_message=payload.message,
                                requester_profile=active_profile,
                            )
                            workflow_event(
                                workflow_logger,
                                "maker_checker_request_created",
                                source="agui",
                                run_id=run_id,
                                thread_id=thread_id,
                                request_id=request_item["request_id"],
                                tool_name=tool_name,
                                metadata={"class": "MakerChecker", "method": "queue"},
                            )
                            queued_result = {
                                "success": True,
                                "queued_for_approval": True,
                                "request_id": request_item["request_id"],
                                "checker_profile": request_item["checker_profile"],
                                "message": (
                                    f"Request queued for checker approval. "
                                    f"Switch to profile '{request_item['checker_profile']}' to approve."
                                ),
                            }
                            forced_followup_text = queued_result["message"]

                            yield sse_event({
                                "type": "MAKER_CHECKER_REQUEST",
                                "request": request_item,
                                "timestamp": now_ms(),
                            })
                            yield sse_event({
                                "type": "MAKER_CHECKER_STATUS",
                                "workflow": {
                                    "total": 4,
                                    "current": 2,
                                    "steps": [
                                        {"name": "Request Captured", "state": "completed"},
                                        {"name": "Awaiting Approval", "state": "current"},
                                        {"name": "Approved", "state": "pending"},
                                        {"name": "Executed", "state": "pending"},
                                    ],
                                },
                                "timestamp": now_ms(),
                            })

                            history.append(ToolMessage(
                                content=json.dumps(queued_result),
                                tool_call_id=tool_call_id
                            ))
                            continue
                        
                        # Execute tool via MCP
                        selected_mcp = get_mcp_server(payload.mcpServer)
                        if selected_mcp:
                            try:
                                result = selected_mcp.execute_tool(tool_name, tool_args)
                                logger.info(f"[{run_id}] Tool {tool_name} executed. Success: {result.get('success', False)}")
                                if tool_name == "terraform_plan" and result.get("success"):
                                    planned_project = (tool_args or {}).get("project_name")
                                    if planned_project:
                                        last_successful_plan_project = planned_project
                                workflow_event(
                                    workflow_logger,
                                    "tool_execution_completed",
                                    source="agui",
                                    run_id=run_id,
                                    thread_id=thread_id,
                                    tool_name=tool_name,
                                    tool_call_id=tool_call_id,
                                    success=result.get("success", False),
                                    tool_result=result,
                                    metadata={"class": "MCPServer", "method": "execute_tool"},
                                )
                                followup_text = build_followup_message(tool_name, result)
                                if followup_text:
                                    forced_followup_text = followup_text
                                
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
                                workflow_event(
                                    workflow_logger,
                                    "tool_execution_failed",
                                    source="agui",
                                    run_id=run_id,
                                    thread_id=thread_id,
                                    tool_name=tool_name,
                                    tool_call_id=tool_call_id,
                                    error=str(tool_err),
                                    metadata={"class": "MCPServer", "method": "execute_tool"},
                                )
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
            if forced_followup_text:
                response_text = forced_followup_text
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
            workflow_event(
                workflow_logger,
                "run_finished",
                source="agui",
                run_id=run_id,
                thread_id=thread_id,
                response_length=len(response_text),
                metadata={"class": "FastAPI", "method": "run_agent.stream"},
            )

            yield sse_event({
                "type": "RUN_FINISHED",
                "runId": run_id,
                "threadId": thread_id,
                "timestamp": now_ms(),
            })

        except Exception as exc:
            logger.error(f"[{run_id}] Error during stream execution: {str(exc)}", exc_info=True)
            workflow_event(
                workflow_logger,
                "run_failed",
                source="agui",
                run_id=run_id,
                thread_id=thread_id,
                error=str(exc),
                metadata={"class": "FastAPI", "method": "run_agent.stream"},
            )
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
